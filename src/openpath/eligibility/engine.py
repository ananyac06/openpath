"""Candidate eligibility evaluation engine.

Enforces non-inferential matching rules:
- Missing requirements are NEVER assumed to be satisfied.
- Independent dimension evaluations for degree, year, discipline, experience, skills, and work authorization.
"""

from __future__ import annotations

import re

from openpath.models.entities import (
    CandidateProfile,
    MatchResult,
    Opportunity,
)


class DimensionEvaluation:
    """Evaluation result for a single eligibility dimension."""

    def __init__(
        self,
        dimension: str,
        result: MatchResult,
        explanation: str,
        raw_requirement: str | None = None,
    ) -> None:
        self.dimension = dimension
        self.result = result
        self.explanation = explanation
        self.raw_requirement = raw_requirement


class EligibilityEvaluationReport:
    """Full eligibility report for a candidate against an opportunity."""

    def __init__(
        self,
        profile_id: str,
        opportunity_id: str,
        overall_result: MatchResult,
        dimension_evaluations: list[DimensionEvaluation],
    ) -> None:
        self.profile_id = profile_id
        self.opportunity_id = opportunity_id
        self.overall_result = overall_result
        self.dimension_evaluations = dimension_evaluations


class EligibilityEngine:
    """Evaluates candidate profiles against extracted opportunity facts."""

    def evaluate(self, profile: CandidateProfile, opportunity: Opportunity) -> EligibilityEvaluationReport:
        desc_text = (opportunity.description_text or "").lower()
        title_text = opportunity.title.lower()
        combined_text = f"{title_text} {desc_text}"

        evaluations: list[DimensionEvaluation] = []

        # 1. Academic Year / Student Status
        year_eval = self._evaluate_academic_year(profile, combined_text)
        evaluations.append(year_eval)

        # 2. Degree Requirement
        degree_eval = self._evaluate_degree(profile, combined_text)
        evaluations.append(degree_eval)

        # 3. Experience Requirement
        exp_eval = self._evaluate_experience(profile, combined_text)
        evaluations.append(exp_eval)

        # 4. Technical Skills
        skills_eval = self._evaluate_skills(profile, combined_text)
        evaluations.append(skills_eval)

        # 5. India Accessibility / Work Authorization
        india_eval = self._evaluate_india_authorization(profile, opportunity, combined_text)
        evaluations.append(india_eval)

        # Overall synthesis
        # If any dimension is CONFIRMED_INELIGIBLE -> overall is CONFIRMED_INELIGIBLE
        # Else if any dimension is UNCLEAR / MORE_INFO_REQUIRED -> overall is UNCLEAR
        # Else all are CONFIRMED_ELIGIBLE -> overall is CONFIRMED_ELIGIBLE
        results = [e.result for e in evaluations]
        if MatchResult.CONFIRMED_INELIGIBLE in results:
            overall = MatchResult.CONFIRMED_INELIGIBLE
        elif MatchResult.UNCLEAR in results or MatchResult.MORE_INFO_REQUIRED in results:
            overall = MatchResult.UNCLEAR
        else:
            overall = MatchResult.CONFIRMED_ELIGIBLE

        return EligibilityEvaluationReport(
            profile_id=profile.id,
            opportunity_id=opportunity.id,
            overall_result=overall,
            dimension_evaluations=evaluations,
        )

    def _evaluate_academic_year(self, profile: CandidateProfile, text: str) -> DimensionEvaluation:
        # Check if text explicitly mentions graduation year or batch
        batch_match = re.search(r"\b(202[4-9]|203[0-2])\s*(?:passout|batch|graduat(?:e|ing|ion))\b", text)
        if batch_match:
            batch_year = int(batch_match.group(1))
            if profile.graduation_year:
                if profile.graduation_year == batch_year:
                    return DimensionEvaluation(
                        "academic_year",
                        MatchResult.CONFIRMED_ELIGIBLE,
                        f"Target graduation batch {batch_year} matches candidate graduation year {profile.graduation_year}.",
                        raw_requirement=batch_match.group(0),
                    )
                else:
                    return DimensionEvaluation(
                        "academic_year",
                        MatchResult.CONFIRMED_INELIGIBLE,
                        f"Listing requires batch {batch_year}; candidate is graduating in {profile.graduation_year}.",
                        raw_requirement=batch_match.group(0),
                    )

        # Check for specific year requirements: "3rd year", "final year", "pre-final year"
        if "final year" in text or "graduating student" in text:
            if profile.academic_year == 4:
                return DimensionEvaluation(
                    "academic_year",
                    MatchResult.CONFIRMED_ELIGIBLE,
                    "Listing targets final-year students; candidate is in year 4.",
                    raw_requirement="final year",
                )
            elif profile.academic_year and profile.academic_year < 4:
                return DimensionEvaluation(
                    "academic_year",
                    MatchResult.CONFIRMED_INELIGIBLE,
                    f"Listing targets final-year students; candidate is in year {profile.academic_year}.",
                    raw_requirement="final year",
                )

        if ("pre-final year" in text or "third year" in text or "3rd year" in text) and profile.academic_year == 3:
            return DimensionEvaluation(
                "academic_year",
                MatchResult.CONFIRMED_ELIGIBLE,
                "Listing targets 3rd/pre-final year students; candidate is in year 3.",
                raw_requirement="3rd year",
            )

        # If it is an internship with no specific year stated:
        if "intern" in text:
            return DimensionEvaluation(
                "academic_year",
                MatchResult.UNCLEAR,
                "Internship role does not explicitly declare eligible academic batches or graduation years.",
            )

        # If full-time fresher / entry level:
        if ("fresher" in text or "trainee" in text or "entry level" in text) and profile.years_experience <= 1.0:
            return DimensionEvaluation(
                "academic_year",
                MatchResult.CONFIRMED_ELIGIBLE,
                "Entry-level/fresher opportunity matches candidate profile (0-1 years exp).",
            )

        return DimensionEvaluation(
            "academic_year",
            MatchResult.UNCLEAR,
            "No explicit academic year or batch requirement found in listing.",
        )

    def _evaluate_degree(self, profile: CandidateProfile, text: str) -> DimensionEvaluation:
        degree_patterns = [
            (r"\bb\.?tech\b|\bb\.?e\.?\b", "B.Tech / B.E."),
            (r"\bm\.?tech\b|\bm\.?e\.?\b", "M.Tech / M.E."),
            (r"\bmca\b", "MCA"),
            (r"\bbca\b", "BCA"),
            (r"\bb\.?sc\b|\bm\.?sc\b", "B.Sc / M.Sc"),
        ]

        mentioned_degrees = []
        for pattern, label in degree_patterns:
            if re.search(pattern, text):
                mentioned_degrees.append(label)

        if not mentioned_degrees:
            return DimensionEvaluation(
                "degree",
                MatchResult.UNCLEAR,
                "No specific degree requirement explicitly specified.",
            )

        cand_degree = (profile.degree or "").upper()
        if any(d in cand_degree for d in ["B.TECH", "BTECH", "BE", "B.E."]) and "B.Tech / B.E." in mentioned_degrees:
            return DimensionEvaluation(
                "degree",
                MatchResult.CONFIRMED_ELIGIBLE,
                f"Candidate degree '{profile.degree}' satisfies required degree '{', '.join(mentioned_degrees)}'.",
            )

        return DimensionEvaluation(
            "degree",
            MatchResult.UNCLEAR,
            f"Listing mentions '{', '.join(mentioned_degrees)}'; candidate degree is '{profile.degree}'.",
        )

    def _evaluate_experience(self, profile: CandidateProfile, text: str) -> DimensionEvaluation:
        # Check for experience requirements like "3+ years", "2-4 years", "4+ years of experience"
        match = re.search(r"\b(\d+)\+?(?:\s*(?:to|-)\s*\d+)?\s*(?:years?|yrs?)(?:\s*of)?\s*experience", text)
        if match:
            min_exp = float(match.group(1))
            raw_req = match.group(0)
            if profile.years_experience >= min_exp:
                return DimensionEvaluation(
                    "experience",
                    MatchResult.CONFIRMED_ELIGIBLE,
                    f"Candidate experience ({profile.years_experience} yrs) meets required minimum ({min_exp} yrs).",
                    raw_requirement=raw_req,
                )
            else:
                return DimensionEvaluation(
                    "experience",
                    MatchResult.CONFIRMED_INELIGIBLE,
                    f"Listing requires at least {min_exp} years experience; candidate has {profile.years_experience} yrs.",
                    raw_requirement=raw_req,
                )

        if "0-1 year" in text or "0 to 1 year" in text or "freshers" in text or "no experience required" in text or "no prior experience" in text:
            return DimensionEvaluation(
                "experience",
                MatchResult.CONFIRMED_ELIGIBLE,
                "Fresher / no experience required matches candidate experience level.",
            )

        return DimensionEvaluation(
            "experience",
            MatchResult.UNCLEAR,
            "Experience requirement not explicitly declared in listing.",
        )

    def _evaluate_skills(self, profile: CandidateProfile, text: str) -> DimensionEvaluation:
        if not profile.skills:
            return DimensionEvaluation(
                "skills",
                MatchResult.UNCLEAR,
                "Candidate profile has no declared technical skills.",
            )

        matched_skills = []
        for skill in profile.skills:
            pattern = rf"\b{re.escape(skill.lower())}\b"
            if re.search(pattern, text):
                matched_skills.append(skill)

        if matched_skills:
            return DimensionEvaluation(
                "skills",
                MatchResult.CONFIRMED_ELIGIBLE,
                f"Matched candidate skills: {', '.join(matched_skills)}.",
            )
        else:
            return DimensionEvaluation(
                "skills",
                MatchResult.UNCLEAR,
                "None of the candidate's declared skills were explicitly mentioned in the text.",
            )

    def _evaluate_india_authorization(
        self, profile: CandidateProfile, opportunity: Opportunity, text: str
    ) -> DimensionEvaluation:
        if opportunity.admission_class == "REJECTED":
            return DimensionEvaluation(
                "india_accessibility",
                MatchResult.CONFIRMED_INELIGIBLE,
                "Opportunity is not accessible to candidates residing in India.",
            )

        # Check explicit location or India eligibility
        loc_str = (opportunity.location_raw or "").lower()
        if "india" in loc_str or any(c in loc_str for c in ["bangalore", "hyderabad", "pune", "mumbai", "delhi", "noida", "gurgaon"]):
            return DimensionEvaluation(
                "india_accessibility",
                MatchResult.CONFIRMED_ELIGIBLE,
                f"Opportunity location confirmed in India: {opportunity.location_raw}",
            )

        if opportunity.work_mode.value == "remote" and ("worldwide" in text or "anywhere" in text or "global" in text):
            return DimensionEvaluation(
                "india_accessibility",
                MatchResult.CONFIRMED_ELIGIBLE,
                "Global remote role accepting applicants worldwide including India.",
            )

        return DimensionEvaluation(
            "india_accessibility",
            MatchResult.UNCLEAR,
            "Location or remote eligibility for Indian applicants is not explicitly verified.",
        )
