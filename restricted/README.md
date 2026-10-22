# restricted/ — données sous licence nominative

Ce répertoire reçoit les fichiers dont la licence interdit la redistribution (DHS, Afrobarometer géocodé, microdonnées de recensement). Voir l'ADR-0028.

**Règles**
- **Hors Git et hors image** : seul ce README est versionné (`.gitignore`, `.dockerignore`).
- **Monté en lecture seule** sur `/restricted` dans les conteneurs `worker` et `cli`. Un manifeste de source en zone `RESTRICTED_LOCAL` ou `SENSITIVE` ne peut lire qu'un chemin sous `/restricted/`.
- **Accès sur l'hôte** :
  - mode 2750 ; ACL en lecture pour l'utilisateur du conteneur (uid 10001), y compris par défaut sur les nouveaux fichiers ;
  - aucun accès pour les autres utilisateurs.
- **Dépôt des fichiers** : c'est le titulaire de l'accès qui les dépose. Leur sha256 va dans le manifeste de source ; l'empreinte ne révèle pas le contenu.
- **Jamais d'affichage** : le contenu n'est jamais affiché dans une conversation, un log ou un rapport. Seuls des agrégats non sensibles en sortent (schéma, comptes de lignes, taux de manquants).

**Mise en place après un clone** (le répertoire doit exister, sinon Docker le crée en root) :

```sh
mkdir -p restricted && chmod 2750 restricted
setfacl -m u:10001:r-x restricted && setfacl -d -m u:10001:r-X restricted
```
