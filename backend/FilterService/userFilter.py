import re
from pathlib import Path

from .filter import FilterService


class UserFilter(FilterService):
    """
    Filter sensitive words for Chilean scams.
    Combines built-in patterns with patterns from a keywords file.
    """

    def __init__(self, keywords_file: str = "user_filtered_words.txt"):
        # Built-in patterns (old ones)
        built_in_patterns = [
            # Credenciales
            r"\b(clave|password|contraseñ?a|passwd|pwd)\b",
            r"\btoken\b",
            r"\bc[oó]digo\s*(de)?\s*(verificaci[oó]n|seguridad)\b",
            r"\bclave\s*d[ií]namica\b",
            r"\bclave\s*secreta\b",
            r"(mi|la)\s+(clave|contraseñ?a)\s+es\s+[^\s]+",
            r"\b\d{4,8}\b(?=.*(clave|pin|token))",
            # Financieros
            r"\bbanco\s*(estado|santander|chile|bci|itau|scotiabank|ripley|falabella|security)\b",
            r"\bn[uú]mero\s+de\s+tarjeta\b",
            r"\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b",
            r"\bCVV\b|\bCVC\b|\bc[oó]digo\s+de\s+seguridad\b",
            r"\bfecha\s+de\s+vencimiento\b",
            r"\bcuenta\s+(vista|corriente|rut)\b",
            r"\brut\b\s*\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]",
            # Personales
            r"\bmi\s+rut\s+es\b",
            r"\bdirecci[oó]n\b",
            r"\bfecha\s+de\s+nacimiento\b",
            r"\btel[eé]fono\b\s*\+?56\s*\d{8,9}",
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            # Entrega involuntaria de información
            r"te\s+paso\s+mi\s+(rut|correo|direccion|clave|token)",
            r"aqu[ií]\s+tienes\s+el\s+c[oó]digo",
            r"el\s+c[oó]digo\s+que\s+me\s+lleg[oó]\s+es\s+\d+",
            # Frases típicas de estafa
            r"ejecutivo\s+del?\s+banco",
            r"somos\s+del?\s+banco",
            r"actualizar\s+datos",
            r"verificar\s+tu\s+cuenta",
            r"bloque[ao]?\s+de\s+cuenta",
            r"validar\s+tu\s+identidad",
            r"transferencia\s+(urgente|inmediata)",
            r"necesito\s+tu\s+c[oó]digo",
            r"p[aá]same\s+(tu|el)\s+(c[oó]digo|token|clave)",
            # Fotos de documentos
            r"\bfoto\s+de\s+mi\s+(carnet|ci|cedula|identidad|tarjeta)\b",
        ]

        # Load additional patterns from file
        file_patterns = self._load_patterns(keywords_file)

        # Combine built-in and file patterns
        all_patterns = built_in_patterns + file_patterns
        super().__init__(all_patterns)

    def _load_patterns(self, file_path: str) -> list[str]:
        path = Path(file_path)
        if not path.exists():
            return []

        patterns = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
        return patterns


def filter_sensitive_words(text: str, filter_instance: UserFilter) -> str:
    """Replace sensitive words in text with 'zzzz'."""
    for pattern in filter_instance.patterns:
        text = re.sub(pattern, "zzzz", text, flags=re.IGNORECASE)
    return text
