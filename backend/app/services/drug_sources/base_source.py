"""
Base class for all drug data source adapters.
Every source must implement the standard interface for fetching
drug information in a normalized format.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NormalizedDrugData:
    """Unified drug data structure that all sources produce."""
    generic_name: str
    brand_names: list[str] = field(default_factory=list)
    drug_class: str = ""
    mechanism_of_action: str = ""
    indications: list[str] = field(default_factory=list)
    adult_dosage: str = ""
    pediatric_dosage: str = ""
    renal_adjustment: str = ""
    hepatic_adjustment: str = ""
    overdose_info: str = ""
    underdose_info: str = ""
    contraindications: str = ""
    black_box_warnings: str = ""
    pregnancy_risk: str = ""
    lactation_risk: str = ""
    interactions: list[dict] = field(default_factory=list)  # [{interacting_drug, severity, description}]
    approximate_cost: str = ""
    generic_available: Optional[bool] = None

    # --- NADAC real pricing fields ---
    nadac_per_unit: Optional[float] = None       # NADAC unit price in USD
    nadac_ndc: str = ""                           # National Drug Code
    nadac_effective_date: str = ""                # NADAC pricing effective date
    nadac_package_description: str = ""           # NDC package description

    # --- Adverse event data (from FDA FAERS) ---
    adverse_event_count: Optional[int] = None     # Total adverse event reports
    adverse_event_serious_count: Optional[int] = None  # Serious reports
    top_adverse_reactions: list[dict] = field(default_factory=list)  # [{reaction, count}]

    # --- Enhanced source attribution ---
    source_authority: str = ""
    source_document_title: str = ""
    source_url: str = ""
    source_year: int = field(default_factory=lambda: datetime.now().year)
    effective_date: str = ""                      # Label effective date (from FDA)
    data_retrieved_at: str = ""                   # ISO timestamp of when data was fetched


class DrugDataSource(ABC):
    """Abstract base class for drug information APIs."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name of this data source."""
        ...

    @property
    @abstractmethod
    def source_authority(self) -> str:
        """Authority backing the data (e.g. 'FDA', 'NIH/NLM')."""
        ...

    @abstractmethod
    def search_drugs(self, query: str, limit: int = 10) -> list[str]:
        """
        Search for drug names matching a query.
        Returns a list of generic drug names.
        """
        ...

    @abstractmethod
    def fetch_drug_data(self, generic_name: str) -> Optional[NormalizedDrugData]:
        """
        Fetch full drug information for a given generic name.
        Returns NormalizedDrugData or None if not found.
        """
        ...

    @abstractmethod
    def fetch_interactions(self, generic_name: str) -> list[dict]:
        """
        Fetch drug-drug interactions for a given drug.
        Returns list of {interacting_drug, severity, description}.
        """
        ...
