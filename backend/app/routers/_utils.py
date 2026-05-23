from fastapi import HTTPException


def raise_for_value_error(e: ValueError) -> None:
    """
    Discriminate between 404 (not found) and 422 (business rule violation).
    Services signal 'not found' by including 'not found' in their ValueError message.
    """
    detail = str(e)
    if "not found" in detail.lower():
        raise HTTPException(status_code=404, detail=detail)
    raise HTTPException(status_code=422, detail=detail)
