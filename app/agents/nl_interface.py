"""Natural language intake routed through the Coordinator's LLM plan interface."""

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.agents.coordinator_agent import CoordinatorAgent
from app.llm.reasoners import LLMReasoner, create_reasoner


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

    def process_request(self, text: str, *, allowed_hospital_ids: Optional[set[int]] = None) -> Dict[str, Any]:
        """Plan natural-language input, then execute via Coordinator/A2A as configured."""
        coordinator = CoordinatorAgent(db=self.db, network=self.network, reasoner=self.reasoner)
        try:
            result = coordinator.coordinate_text(text, persist=False, allowed_hospital_ids=allowed_hospital_ids)
        except (ValueError, RuntimeError) as exc:
            return {
                "success": False,
                "status": "PLANNING_ERROR",
                "message": str(exc),
                "extracted_fields": {},
                "structured_result": None,
            }

        plan = result.get("plan", {})
        extracted = dict(plan)
        if plan.get("location"):
            hospital = self._find_hospital(plan["location"])
            if hospital:
                extracted.update({"hospital_id": hospital.hospital_id, "hospital_name": hospital.name})

        if result.get("status") == "NEEDS_CLARIFICATION":
            return {
                "success": False,
                "status": "NEEDS_CLARIFICATION",
                "message": result.get("clarification_question", "Please clarify the request."),
                "extracted_fields": extracted,
                "structured_result": None,
                "llm": result.get("llm"),
            }
        if not result.get("success"):
            return {
                "success": False,
                "status": "FAILED",
                "message": f"Request could not be fulfilled: {result.get('error')}.",
                "extracted_fields": extracted,
                "structured_result": result,
            }

        plan_result = result.get("fulfillment_plan", {})
        total_units = plan_result.get("total_units", 0)
        units_required = result.get("requirement", {}).get("units_required", 0)
        sources_count = len(plan_result.get("plan", []))
        summary = (
            f"Successfully processed request for {plan.get('location')}: "
            f"{total_units}/{units_required} units of {plan.get('blood_group')} secured "
            f"across {sources_count} source(s). Plan status: {plan_result.get('status', 'COMPLETED')}."
        )
        return {
            "success": True,
            "status": plan_result.get("status", "COMPLETED"),
            "message": summary,
            "extracted_fields": extracted,
            "structured_result": result,
        }
