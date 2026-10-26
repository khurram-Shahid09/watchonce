from rest_framework.throttling import SimpleRateThrottle


class TokenRateThrottle(SimpleRateThrottle):
    """General API limit per credential: each personal access token on its own, and the
    dashboard's session tokens per user. Anonymous calls are left to the login throttles."""

    scope = "token"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        from accounts.models import ApiToken

        auth = request.auth
        ident = f"token:{auth.pk}" if isinstance(auth, ApiToken) else f"user:{user.pk}"
        return self.cache_format % {"scope": self.scope, "ident": ident}
