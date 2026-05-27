"""Backward-compatible import path for the canonical defect classifier."""

from agentManager.defect_repair.classifier import DefectClassifier, DefectPattern, SeverityLevel
from agentManager.defect_repair.repair_engine import RepairLevel

__all__ = ["DefectClassifier", "DefectPattern", "RepairLevel", "SeverityLevel"]
