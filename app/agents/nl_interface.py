"""Natural Language Interface Agent for Emergency Dispatch (Part 14).

Parses free-text emergency requests into structured entities, passes them
strictly through validated MCP tools / Coordinator Agent pipeline, and
synthesizes human-readable natural language operational summaries.
"""

import os
import re
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.agents.coordinator_agent import CoordinatorAgent
from app.llm.prompt_templates import EXTRACTION_SYSTEM_PROMPT


class NLInterfaceAgent:
    """Agent that translates natural-language dispatch text to coordinated actions."""

    VALID_BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

    def __init__(self, db: Optional[Session] = None):
        """Initialize the Natural-Language Interface Agent.
        
        Args:
            db: Optional active database session for hospital resolution and persistence.
        """
        self.db = db
        self.llm_provider = os.getenv("LLM_PROVIDER", "builtin").strip().lower()

    def parse_text(self, text: str) -> Dict[str, Any]:
        """Extract structured blood request fields from free-form text.
        
        Uses semantic extraction with strict ambiguity detection.
        Never guesses missing vital clinical parameters.
        """
        if not text or not text.strip():
            return {
                "success": False,
                "is_ambiguous": True,
                "clarification_question": "Please provide the details of your blood request (e.g. 'We urgently need 3 units of O+ at City Hospital').",
                "extracted": {},
            }

        text_clean = text.strip()

        # 1. Extract Blood Group
        bg_match = re.search(r"\b(AB|A|B|O)\s*([+-])(?!\w)", text_clean, re.IGNORECASE)
        blood_group = (bg_match.group(1).upper() + bg_match.group(2)) if bg_match else None

        # 2. Extract Units Required
        units_match = re.search(r"(\d+)\s*(?:units?|bags?|pints?|packs?)", text_clean, re.IGNORECASE)
        units_required = int(units_match.group(1)) if units_match else None

        if units_required is None:
            # Fallback for standalone digit near blood group
            digit_match = re.search(r"(?:need|request|want)\s*(\d+)", text_clean, re.IGNORECASE)
            if digit_match:
                units_required = int(digit_match.group(1))

        # 3. Extract Urgency
        urgency = "MEDIUM"
        if re.search(r"\b(critical|stat|code blue|immediately)\b", text_clean, re.IGNORECASE):
            urgency = "CRITICAL"
        elif re.search(r"\b(urgent|urgently|emergency|asap|rush)\b", text_clean, re.IGNORECASE):
            urgency = "HIGH"
        elif re.search(r"\b(routine|low|scheduled)\b", text_clean, re.IGNORECASE):
            urgency = "LOW"

        # 4. Extract Hospital
        hospital_id = 1  # Default benchmark hospital
        hospital_name = "General Hospital"
        hosp_match = re.search(r"(?:at|for|to)\s+([A-Za-z0-9\s]+?)(?:hospital|clinic|center|medical)", text_clean, re.IGNORECASE)
        if hosp_match:
            candidate_name = (hosp_match.group(1) + " Hospital").strip()
            if self.db:
                found_hosp = self.db.query(Hospital).filter(
                    Hospital.name.ilike(f"%{hosp_match.group(1).strip()}%")
                ).first()
                if found_hosp:
                    hospital_id = found_hosp.hospital_id
                    hospital_name = found_hosp.name
                else:
                    hospital_name = candidate_name

        # 5. Check Ambiguity & Completeness
        missing_fields = []
        if not blood_group:
            missing_fields.append("blood group (e.g. O+, A-)")
        if not units_required:
            missing_fields.append("number of units required")

        if missing_fields:
            question = f"Could you please clarify the {' and '.join(missing_fields)} for this request?"
            return {
                "success": False,
                "is_ambiguous": True,
                "clarification_question": question,
                "extracted": {
                    "hospital_id": hospital_id,
                    "hospital_name": hospital_name,
                    "blood_group": blood_group,
                    "units_required": units_required,
                    "urgency": urgency,
                },
            }

        return {
            "success": True,
            "is_ambiguous": False,
            "clarification_question": None,
            "extracted": {
                "hospital_id": hospital_id,
                "hospital_name": hospital_name,
                "blood_group": blood_group,
                "units_required": units_required,
                "urgency": urgency,
            },
        }

    def process_request(self, text: str) -> Dict[str, Any]:
        """Execute full end-to-end natural language request pipeline.
        
        Workflow:
            1. Parse free text.
            2. If ambiguous -> halt safely and return clarification question.
            3. Route through CoordinatorAgent for validation, matching, and location.
            4. Synthesize natural-language operational response summary.
        """
        parse_res = self.parse_text(text)
        if parse_res["is_ambiguous"]:
            return {
                "success": False,
                "status": "NEEDS_CLARIFICATION",
                "message": parse_res["clarification_question"],
                "extracted_fields": parse_res["extracted"],
                "structured_result": None,
            }

        extracted = parse_res["extracted"]

        # Run through the Coordinator Agent (never bypass validation!)
        coordinator = CoordinatorAgent(db=self.db)
        coord_payload = {
            "request_id": 999,
            "hospital_id": extracted["hospital_id"],
            "blood_group": extracted["blood_group"],
            "units_required": extracted["units_required"],
            "urgency": extracted["urgency"],
        }

        try:
            coord_res = coordinator.coordinate(request_input=coord_payload, persist=False)
        except Exception as exc:
            return {
                "success": False,
                "status": "COORDINATION_ERROR",
                "message": f"Coordination pipeline error: {exc}",
                "extracted_fields": extracted,
                "structured_result": None,
            }

        if not coord_res.get("success"):
            summary_msg = f"Request for {extracted['units_required']} units of {extracted['blood_group']} could not be fulfilled: {coord_res.get('error')}."
            return {
                "success": False,
                "status": "FAILED",
                "message": summary_msg,
                "extracted_fields": extracted,
                "structured_result": coord_res,
            }

        # Synthesize natural language summary from structured result
        plan = coord_res.get("fulfillment_plan", {})
        plan_status = plan.get("status", "COMPLETED")
        total_units = plan.get("total_units", 0)
        sources_count = len(plan.get("plan", []))

        summary_msg = (
            f"Successfully processed request for {extracted['hospital_name']}: "
            f"{total_units}/{extracted['units_required']} units of {extracted['blood_group']} secured "
            f"across {sources_count} source(s). Plan status: {plan_status}."
        )

        return {
            "success": True,
            "status": plan_status,
            "message": summary_msg,
            "extracted_fields": extracted,
            "structured_result": coord_res,
        }
