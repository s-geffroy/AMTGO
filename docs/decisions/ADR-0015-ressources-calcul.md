# ADR-0015 — Ressources de calcul : threads BLAS et SciPy

*Statut : accepté — 2026-10-20.*

## Contexte
Profilage M3 (prompt §81) : une résolution 300 × 300 prenait 0,25 s (×200). Le
conteneur voit tous les cœurs de l'hôte mais son quota est de 1 CPU : OpenBLAS
lançait un thread par cœur, en attente active sur un seul CPU. Par ailleurs,
la formation de $J V_0 J^\top$ en dense coûtait O(M²N) à chaque itération,
alors que J est très creuse.

## Décision
- `OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1` dans l'image, aligné
  sur `cpus: "1.0"`. À réviser si le quota change.
- **SciPy** ajouté (matrices creuses), dépendance justifiée par le profilage.

## Effet mesuré
Pilote synthétique complet : 193 s → 16,8 s. Suite de tests : 478 s → 65 s.
