"""Portable records for imported interview experiences and reference answers."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MaterialKind = Literal["interview", "answer"]


class MaterialModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceBlock(MaterialModel):
    location: str = Field(min_length=1)
    text: str
    method: str = Field(default="text", min_length=1)


class DocumentRead(MaterialModel):
    blocks: list[SourceBlock]
    warnings: list[str] = Field(default_factory=list)


class MaterialItem(MaterialModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    kind: MaterialKind
    title: str = ""
    question: str = ""
    answer: str = ""
    followups: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    company: str = ""
    role: str = ""
    source_file: str = Field(min_length=1)
    location: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)


class MaterialDocument(MaterialModel):
    id: str = Field(min_length=1)
    kind: MaterialKind
    filename: str = Field(min_length=1)
    source_file: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    imported_at: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    company: str = ""
    role: str = ""
    blocks: list[SourceBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    item_ids: list[str] = Field(default_factory=list)
    extraction_method: str = "offline"


class MaterialState(MaterialModel):
    schema_version: int = 1
    documents: list[MaterialDocument] = Field(default_factory=list)
    items: list[MaterialItem] = Field(default_factory=list)
