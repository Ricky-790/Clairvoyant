from pydantic import BaseModel


class StartIngestionRequest(BaseModel):
    installation_id: int
    repo_id: int  # GitHub's numeric repo id
    repo_full_name: str

class StandardResponse(BaseModel):
    message: str
