from pydantic import AnyUrl, UrlConstraints


class ValkeyDns(AnyUrl):
    """A type that will accept any Valkey DSN.

    * User info required
    * TLD not required
    * Host required (e.g., `valkey://:pass@localhost`)
    """

    _constraints = UrlConstraints(
        allowed_schemes=['valkey', 'valkeys', 'unix'],
        default_host='localhost',
        default_port=6379,
        default_path='/0',
        host_required=True,
    )

    @property
    def host(self) -> str:
        """The required URL host."""
        return self._url.host  # pyright: ignore[reportReturnType]
