from flask import request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity


def current_identity():
    """
    Returns (user_id, anon_id). JWT is optional on the public-facing
    content endpoints — logged-in users get a persistent personalized
    context, anonymous visitors get one keyed off the client-generated
    X-Anon-Id header (see frontend lib/api.js).
    """
    user_id = None
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity:
            user_id = int(identity)
    except Exception:
        user_id = None

    anon_id = request.headers.get('X-Anon-Id') if user_id is None else None
    return user_id, anon_id
