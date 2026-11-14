# Voix ElevenLabs

Dans `.env`, ajoute ta clé personnelle (ne la partage pas) :

```dotenv
ELEVENLABS_API_KEY=ta_cle_elevenlabs
```

Relance l'app. Dans **Service vocal**, choisis **ElevenLabs**, puis **Charger mes voix ElevenLabs**. Sélectionne une voix française et clique **Utiliser cette voix**. Tu peux aussi saisir directement son identifiant.

Choisis Multilingual v2 ou Eleven v3. Dans une scène avec dialogue, clique **Écouter la voix** avant de générer la vidéo. Le MP3 ElevenLabs est conservé par projet et réutilisé pour le même texte, la même voix et le même modèle : la vidéo reçoit donc l'audio écouté. Modifier ces paramètres crée un nouvel audio. Chaque nouvel audio consomme les crédits de ton compte. Les clips existants ne sont pas régénérés automatiquement.

Microsoft Edge reste disponible. Les réglages de vitesse et hauteur Edge ne concernent pas ElevenLabs. Les paroles trop longues doivent être corrigées et confirmées avant la génération vidéo.

API : https://elevenlabs.io/docs/api-reference/text-to-speech/convert
