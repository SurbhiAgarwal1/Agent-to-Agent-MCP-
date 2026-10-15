"""Natural language intake routed through the Coordinator's LLM plan interface."""

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.agents.coordinator_agent import CoordinatorAgent
from app.llm.reasoners import LLMReasoner, create_reasoner

from datetime import datetime, timezone

from app.models.blood_request import BloodRequest
from app.models.enums import RequestStatus


class NLInterfaceAgent:
    """Translate user text into a validated Coordinator plan and final response."""

    def __init__(
        self,
        db: Optional[Session] = None,
        network: bool = False,
        reasoner: Optional[LLMReasoner] = None,
    ) -> None:
        self.db = db
        self.network = network
        self.reasoner = reasoner or create_reasoner()

    def parse_text(self, text: str) -> Dict[str, Any]:
        """Return validated structured fields or a safe clarification request."""
        if not text or not text.strip():
            return self._clarification({}, ["blood group", "number of units", "hospital or location"])
        try:
            coordinator = CoordinatorAgent(db=self.db, network=self.network, reasoner=self.reasoner)
            plan, metadata = coordinator.generate_plan(text)
        except (ValueError, RuntimeError) as exc:
            return {"success": False, "is_ambiguous": True, "error": str(exc), "extracted": {}}

        extracted = plan.model_dump(mode="json")
        missing = []
        if not plan.blood_group:
            missing.append("blood group")
        if not plan.units_required:
            missing.append("number of units")
        if not plan.location:
            missing.append("hospital or location")
        if missing:
            return self._clarification(extracted, missing, metadata)

        hospital = self._find_hospital(plan.location)
        if hospital is None:
            return self._clarification(
                extracted,
                ["registered hospital matching the requested location"],
                metadata,
                question=f"I couldn't match '{plan.location}' to a registered hospital. Please specify one.",
            )
        extracted.update({"hospital_id": hospital.hospital_id, "hospital_name": hospital.name})
        return {
            "success": True,
            "is_ambiguous": False,
            "clarification_question": None,
            "extracted": extracted,
            "plan": plan.model_dump(mode="json"),
            "llm": metadata,
        }

    def _find_hospital(self, location: str):
        if self.db is None:
            return None
        from sqlalchemy import or_
        from app.models.hospital import Hospital

        needle = f"%{location}%"
        return self.db.query(Hospital).filter(
            or_(Hospital.name.ilike(needle), Hospital.address.ilike(needle))
        ).first()

    @staticmethod
    def _clarification(
        extracted: dict,
        missing: list[str],
        metadata: dict | None = None,
        question: str | None = None,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "is_ambiguous": True,
            "clarification_question": question or "Please provide the " + " and ".join(missing) + ".",
            "missing_fields": missing,
            "extracted": extracted,
            "llm": metadata,
        }

    def process_request(
    self,
    text: str,
    *,
    current_user_id: int,
    allowed_hospital_ids: Optional[set[int]] = None,
) -> Dict[str, Any]:
    #Parse a natural-language request, persist it, then coordinate it.
        coordinator = CoordinatorAgent(
            db=self.db,
            network=self.network,
            reasoner=self.reasoner,
        )

        try:
            plan, llm_metadata = coordinator.generate_plan(text)
        except (ValueError, RuntimeError) as exc:
            return {
                "success": False,
                "status": "PLANNING_ERROR",
                "message": str(exc),
                "extracted_fields": {},
                "structured_result": None,
            }

        extracted = plan.model_dump(mode="json")

        if not plan.blood_group or not plan.units_required or not plan.location:
            missing = []

            if not plan.blood_group:
                missing.append("blood group")
            if not plan.units_required:
                missing.append("number of units")
            if not plan.location:
                missing.append("hospital/location")

            return {
                "success": False,
                "status": "NEEDS_CLARIFICATION",
                "message": f"Please provide {', '.join(missing)}.",
                "extracted_fields": extracted,
                "structured_result": None,
                "llm": llm_metadata,
            }

        hospital = self._find_hospital(plan.location)

        if not hospital:
            return {
                "success": False,
                "status": "FAILED",
                "message": f"No hospital could be found for {plan.location}.",
                "extracted_fields": extracted,
                "structured_result": None,
                "llm": llm_metadata,
            }

        if (
            allowed_hospital_ids is not None
            and hospital.hospital_id not in allowed_hospital_ids
        ):
            return {
                "success": False,
                "status": "FAILED",
                "message": "You are not authorized to create a request for this hospital.",
                "extracted_fields": extracted,
                "structured_result": None,
                "llm": llm_metadata,
            }

        if self.db is None:
            return {
                "success": False,
                "status": "FAILED",
                "message": "Database is unavailable.",
                "extracted_fields": extracted,
                "structured_result": None,
                "llm": llm_metadata,
            }

        new_request = BloodRequest(
            hospital_id=hospital.hospital_id,
            created_by_user_id=current_user_id,
            blood_group=plan.blood_group,
            units_required=plan.units_required,
            urgency=plan.urgency.value,
            status=RequestStatus.PENDING.value,
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(new_request)
        self.db.commit()
        self.db.refresh(new_request)

        extracted.update(
            {
                "request_id": new_request.request_id,
                "hospital_id": hospital.hospital_id,
                "hospital_name": hospital.name,
            }
        )

        try:
            result = coordinator.coordinate(
                new_request.request_id,
                persist=True,
            )
        except (ValueError, RuntimeError) as exc:
            return {
                "success": False,
                "status": "FAILED",
                "message": str(exc),
                "extracted_fields": extracted,
                "structured_result": None,
                "llm": llm_metadata,
            }

        if not result.get("success"):
            return {
                "success": False,
                "status": "FAILED",
                "message": f"Request could not be fulfilled: {result.get('error')}.",
                "extracted_fields": extracted,
                "structured_result": result,
                "llm": llm_metadata,
            }

        plan_result = result.get("fulfillment_plan", {})
        total_units = plan_result.get("total_units", 0)
        units_required = result.get("requirement", {}).get(
            "units_required",
            plan.units_required,
        )
        sources_count = len(plan_result.get("plan", []))

        summary = (
            f"Successfully processed request for {plan.location}: "
            f"{total_units}/{units_required} units of {plan.blood_group} secured "
            f"across {sources_count} source(s). "
            f"Plan status: {plan_result.get('status', 'COMPLETED')}."
        )

        return {
            "success": True,
            "status": plan_result.get("status", "COMPLETED"),
            "message": summary,
            "extracted_fields": extracted,
            "structured_result": result,
            "llm": llm_metadata,
        }