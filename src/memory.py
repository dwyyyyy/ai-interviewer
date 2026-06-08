from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TurnEvaluation(BaseModel):
    answer_summary: str = ""
    observations: list[str] = Field(default_factory=list)
    covered_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    risk_flags: list[dict[str, Any]] = Field(default_factory=list)
    need_follow_up: bool = False
    direction_complete: bool = False
    signal_sufficient: bool = False
    candidate_admitted_gap: bool = False
    new_information_gain: Literal["low", "medium", "high"] = "medium"


class ConversationTurn(BaseModel):
    round: int
    stage: str
    stage_name: str
    question: str
    answer: str
    question_type: str
    focus_area: str
    evaluation: TurnEvaluation


class DirectionScore(BaseModel):
    direction: str
    stage: str
    verification_level: int = 1
    level_label: str = "未验证"
    judgement: str = ""
    evidence: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    suggestion: str = ""
    confidence: Literal["low", "medium", "high"] = "medium"
    related_rounds: list[int] = Field(default_factory=list)


class InterviewMemory(BaseModel):
    stages: list[dict[str, Any]]
    current_stage_index: int = 0
    current_round: int = 1
    stage_round_index: int = 0
    conversation: list[ConversationTurn] = Field(default_factory=list)
    asked_questions: list[str] = Field(default_factory=list)
    covered_dimensions: list[str] = Field(default_factory=list)
    open_risks: list[str] = Field(default_factory=list)
    resolved_risks: list[str] = Field(default_factory=list)
    direction_scores: list[DirectionScore] = Field(default_factory=list)
    consecutive_followups: int = 0

    @classmethod
    def from_plan(cls, plan: dict) -> "InterviewMemory":
        return cls(stages=plan.get("stages", []))

    @property
    def current_stage(self) -> dict[str, Any]:
        if self.current_stage_index >= len(self.stages):
            return {"id": "final_report", "name": "评估报告", "demo_rounds": 0}
        return self.stages[self.current_stage_index]

    @property
    def current_stage_id(self) -> str:
        return self.current_stage.get("id", "unknown")

    @property
    def current_stage_name(self) -> str:
        return self.current_stage.get("name", self.current_stage_id)

    def recent_turns(self, limit: int = 3) -> list[dict]:
        return [turn.model_dump() for turn in self.conversation[-limit:]]

    def record_turn(self, question: dict, answer: str, evaluation_data: dict) -> None:
        evaluation = TurnEvaluation(**evaluation_data)
        self.conversation.append(
            ConversationTurn(
                round=self.current_round,
                stage=self.current_stage_id,
                stage_name=self.current_stage_name,
                question=question["question"],
                answer=answer,
                question_type=question.get("question_type", "new_topic"),
                focus_area=question.get("focus_area", self.current_stage_name),
                evaluation=evaluation,
            )
        )
        self.asked_questions.append(question["question"])
        for point in evaluation.covered_points:
            if point not in self.covered_dimensions:
                self.covered_dimensions.append(point)
        for risk in evaluation.risk_flags:
            risk_text = risk.get("risk") or risk.get("point")
            if risk_text and risk_text not in self.open_risks:
                self.open_risks.append(risk_text)

    def continue_current_direction(self) -> None:
        self.consecutive_followups += 1
        self.stage_round_index += 1
        self.current_round += 1

    def advance_to_next_direction(self) -> None:
        self.consecutive_followups = 0
        self._advance_round_or_stage()

    def current_stage_limit_reached(self) -> bool:
        return self.stage_round_index + 1 >= int(self.current_stage.get("demo_rounds", 1))

    def followup_limit_reached(self) -> bool:
        return self.consecutive_followups >= 2

    @property
    def latest_evaluation(self) -> TurnEvaluation | None:
        if not self.conversation:
            return None
        return self.conversation[-1].evaluation

    @property
    def current_direction_turns(self) -> list[ConversationTurn]:
        if not self.conversation:
            return []
        focus = self.conversation[-1].focus_area
        turns = []
        for turn in reversed(self.conversation):
            if turn.focus_area != focus:
                break
            turns.append(turn)
        return list(reversed(turns))

    def add_direction_score(self, score_data: dict[str, Any]) -> None:
        if any(score.direction == score_data.get("direction") and score.related_rounds == score_data.get("related_rounds") for score in self.direction_scores):
            return
        self.direction_scores.append(DirectionScore(**score_data))

    def _advance_round_or_stage(self) -> None:
        self.current_round += 1
        self.stage_round_index += 1
        stage_rounds = int(self.current_stage.get("demo_rounds", 1))
        if self.stage_round_index >= stage_rounds:
            self.current_stage_index += 1
            self.stage_round_index = 0

    def should_finish(self) -> bool:
        return self.current_stage_index >= len(self.stages)

    def summary(self) -> dict:
        return {
            "current_stage": self.current_stage_name,
            "current_round": self.current_round,
            "stage_round_index": self.stage_round_index,
            "asked_count": len(self.asked_questions),
            "covered_dimensions": self.covered_dimensions,
            "open_risks": self.open_risks,
            "direction_scores": [score.model_dump() for score in self.direction_scores],
            "consecutive_followups": self.consecutive_followups,
        }

    def collect_strengths(self) -> list[str]:
        strengths = []
        for turn in self.conversation:
            strengths.extend(turn.evaluation.strengths)
        return list(dict.fromkeys(strengths))

    def collect_observations(self) -> list[str]:
        observations = []
        for turn in self.conversation:
            observations.extend(turn.evaluation.observations)
        return list(dict.fromkeys(observations))
