# Studio de scènes

Lancement depuis la racine du projet :

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Après une mise à jour des modules Python, arrêter l'ancien serveur avec Ctrl+C et relancer cette commande. Utiliser le fichier de ce projet, pas une copie dans Téléchargements.

## Deux studios en parallèle

Pour ouvrir deux onglets avec deux comptes Agnes indépendants :

```powershell
.\.venv\Scripts\python.exe start_studios.py
```

- http://localhost:8501 utilise `AGNES_API_KEY`.
- http://localhost:8502 utilise `AGNES_API_KEY2`.

Les deux clés doivent être présentes dans `.env`. Les deux studios partagent les mêmes projets dans `videos/jobs/`, ainsi que les médias et imports. Un projet créé sur un port peut être chargé sur l'autre avec le même nom et le bouton « Charger le projet ». Ce bouton recharge les données enregistrées ; les changements ne sont pas synchronisés en direct entre les onglets. Modifier ou générer un même projet dans un seul studio à la fois pour éviter les écrasements. Deux projets différents peuvent être traités en parallèle. Chaque studio affiche son numéro dans la barre latérale. Les autres services, comme ElevenLabs, gardent leur configuration commune.

Arrêter un éventuel serveur déjà lancé sur ces ports avant cette commande. Garder le terminal ouvert ; Ctrl+C arrête les deux studios. La commande habituelle `streamlit run app.py` lance toujours un seul studio, avec le premier compte par défaut.

## Organisation

Les nouvelles tâches vidéo mémorisent une empreinte de leur clé Agnes (jamais la clé elle-même). Leur suivi reprend avec le compte d'origine, même depuis l'autre port. Pour une ancienne tâche sans empreinte, une réponse 404 entraîne une vérification avec l'autre clé configurée, sans soumettre de nouvelle génération. Les nouvelles générations utilisent toujours la clé du studio courant.

- `app.py` : point d'entrée et vérification de compatibilité.
- `src/studio/views.py` : composition de la page.
- `src/studio/settings.py` : réglages du projet et de l'audio.
- `src/studio/scenes.py` : ajout et liste des scènes.
- `src/studio/scene_editor.py` : coordination de l'édition et de la validation d'une scène.
- `src/studio/image_panel.py`, `prompt_panel.py` : édition de l'image et du prompt.
- `src/studio/delivery.py` : suivi de production et assemblage.
- `src/studio/actions.py` : actions liées à la session et au projet.
- `src/studio/theme.py`, `studio.css` et `.streamlit/config.toml` : présentation.
- `src/scene_video_production.py`, `video_pipeline.py`, `production_state.py` : génération et règles de validation, indépendantes des composants d'interface.

## Direction visuelle

Fond clair neutre, contraste lisible, bordures fines, accent vert foncé réservé aux actions principales. Les images et prompts restent prioritaires. Les réglages avancés sont repliés, les statuts sont textuels, sans dépendre uniquement de la couleur. Aucun chargement de polices ou de scripts externes.

## Vérification sans crédits API

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_studio_runtime.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_scene_video_production.py
```
