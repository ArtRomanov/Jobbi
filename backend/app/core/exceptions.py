from fastapi import HTTPException, status


def not_found(resource: str = "Resource") -> HTTPException:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found.",
    )
