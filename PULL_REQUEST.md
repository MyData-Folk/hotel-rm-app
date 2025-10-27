# Revert changes after e547fa5c56f0 — restore snapshot 'version deepsite'

### Objectif : 
Annuler tous les changements introduits après le commit e547fa5c56f03918b5712d69c1bc03fe86995149 afin de restaurer l’état correspondant à ce snapshot.

### Actions effectuées :
- Création d’une branche de sauvegarde backup-main-before-revert (poussée)
- Branche de travail revert-to-e547fa5c créée depuis main
- Cette PR contient les commits de revert annulant les changements postérieurs au commit cible.

### Procédure de validation : 
lancer la CI et vérifier localement les principales fonctionnalités avant merge.

### Remarque : 
L’historique est préservé (les commits annulés restent visibles mais sont compensés par les commits de revert). Si vous souhaitez une réécriture destructive de l’historique (reset --hard + force-push), confirmez explicitement.