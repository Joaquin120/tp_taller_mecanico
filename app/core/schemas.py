from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Contrato base Pydantic que prohíbe atributos adicionales en payloads."""

    model_config = ConfigDict(extra="forbid")
