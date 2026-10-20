"""Taxonomie d'erreurs AMTGO (prompt §71).

Chaque erreur porte un sens scientifique ou normatif précis. Ne jamais les
attraper pour les transformer en valeur par défaut : une erreur avalée est une
hypothèse cachée.
"""


class AMTGOError(Exception):
    """Racine de toutes les erreurs AMTGO."""


class DataLicenseError(AMTGOError):
    """Une licence interdit l'usage, la redistribution ou l'usage commercial demandé."""


class PrivacyViolation(AMTGOError):
    """Une sortie dépasserait la classe d'accès autorisée (individuelle, de groupe, politique)."""


class InsufficientEvidence(AMTGOError):
    """Le support empirique ne permet pas le calcul demandé : réponse honnête = UNKNOWN."""


class CausalUnsupported(AMTGOError):
    """Aucun effet causal admissible : CAUSAL_EFFECT_UNKNOWN, jamais un coefficient inventé."""


class InfeasibleOptimization(AMTGOError):
    """Contraintes incompatibles : un certificat d'infaisabilité est obligatoire."""


class TopologyError(AMTGOError):
    """Invariant topologique violé (géométrie invalide, chevauchement, parentage incohérent)."""


class OntologyMappingError(AMTGOError):
    """Crosswalk absent, incohérent ou non probabiliste entre ontologies."""


class ReproducibilityError(AMTGOError):
    """Même manifeste et même code n'ont pas produit le même résultat."""


class ProvenanceError(AMTGOError):
    """Une sortie n'est pas traçable jusqu'à ses sources (prompt §10, §57)."""


class ConfigurationError(AMTGOError):
    """Configuration ou manifeste invalide."""


class ForbiddenSourceRole(AMTGOError):
    """Usage d'une source dans un rôle interdit ou non déclaré par son manifeste (03, prompt §69)."""


class StageInterrupted(AMTGOError):
    """Arrêt demandé (SIGTERM) au milieu d'une étape : elle sera rejouée, ce n'est pas un échec."""


class NormativeViolation(AMTGOError):
    """Un invariant normatif serait violé (prompt §86) : déplacement forcé, plan de coercition…"""
