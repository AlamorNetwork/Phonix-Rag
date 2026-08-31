from pydantic import BaseModel


class ModelResponse(BaseModel):
    id: str
    provider_id: str
    model_id: str
    input_price_per_1k: float
    output_price_per_1k: float
    context_window: int
    enabled: bool

    class Config:
        from_attributes = True


class ProviderResponse(BaseModel):
    id: str
    name: str
    base_url: str

    class Config:
        from_attributes = True
