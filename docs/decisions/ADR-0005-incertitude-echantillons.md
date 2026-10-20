# ADR-0005 — UncertainValue fondé sur des tirages

*Statut : accepté — 2026-10-20.*

## Contexte
Le prompt §65 propose `UncertainValue(mean, std, lower, upper, distribution_type)`.
Or les contraintes de droits sont probabilistes, $P(d_{gkd}>\tau_d)\le\epsilon_d$,
et l'objectif robuste utilise une CVaR (02 §18). Un résumé à quatre nombres ne
permet ni l'un ni l'autre sans supposer une loi.

## Décision
`samples` (tirages d'un postérieur, d'un ensemble ou d'un bootstrap) est la
source de vérité quand présente ; le résumé en est dérivé. Sans tirages,
`exceedance_probability` et `cvar` lèvent `InsufficientEvidence` au lieu
d'inventer une loi. Types : `EMPIRICAL`, `NORMAL`, `UNIFORM`, `POINT`
(constante définie), `UNKNOWN` (bornes seules, identification partielle 04 §11).

## Conséquences
Coût mémoire proportionnel au nombre de tirages ; à profiler en M3.
