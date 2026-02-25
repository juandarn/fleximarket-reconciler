"""Abstract base class for all settlement file parsers."""

from abc import ABC, abstractmethod
from typing import List

from app.schemas.settlement import SettlementCreate


class BaseParser(ABC):
    """Base interface that every processor-specific parser must implement.

    Each parser is responsible for:
    1. Reading raw file bytes in the processor's format (CSV, JSON, XML, etc.)
    2. Normalizing field names to our internal SettlementCreate schema
    3. Handling malformed rows gracefully (skip + log, never crash)
    """

    processor_name: str

    @abstractmethod
    def parse(self, file_content: bytes, filename: str) -> List[SettlementCreate]:
        """Parse file content and return normalized settlement entries.

        Args:
            file_content: Raw bytes of the uploaded file.
            filename: Original filename (used for source_file tracking).

        Returns:
            A list of SettlementCreate objects ready for DB insertion.
        """
        pass
