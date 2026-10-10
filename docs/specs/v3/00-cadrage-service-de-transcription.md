# V3 — Cadrage : `roles` devient un service de transcription

> **Statut : cadrage en cours.** Décisions acquises au **2026-10-10**, lors d'un échange avec
> l'architecte. Ce document est la **trace** de ce cadrage : il dit ce qui est tranché, ce qui
> reste ouvert, et les tensions qu'il faudra lever. Il n'est pas une spécification
> d'implémentation.
>
> Les specs `docs/specs/v2/` décrivent l'état **antérieur**. Elles restent utiles pour comprendre
> le code en place ; elles ne font plus foi pour décider.

## La demande de départ, mot pour mot

> « Je veux simplifier le module. Une api pour fournir du travail avec un webhook optionnel dans
> les paramètres qui nous permet de rappeler quand le travail est finis. La méthode renvoie un
> identifiant unique de travail. Une api de pooling avec l'identifiant »

Elle est conservée telle quelle : c'est le point de contrôle. Si ce qui est construit ne sert pas
ce qu'elle visait, soit quelque chose a été raté, soit il y a un écart à expliquer.

---

## Décisions acquises

### 1. Deux formes d'entrée, et aucune sélection

Une **URL de chaîne** (on prend tout) ou une **URL de vidéo**. Plus de découverte exposée, plus
d'examen humain, plus de choix, plus de filtres.

Tombent : `list_discovered`, `select_items`, les filtres (`max_items`, `since`,
`min/max_duration_s`), les états `discovered` / `selected` des items.

La découverte **survit comme mécanisme** — il faut bien énumérer une chaîne — elle cesse d'être un
point de décision.

### 2. L'identifiant de chaîne est un index, pas un résultat

- `POST` une vidéo → un id qui **porte le résultat** ;
- `POST` une chaîne → un id **maître** dont le pooling rend **la liste des ids de vidéos**, et non
  leurs résultats. Le résultat se récupère id par id.

**Un id présent dans la liste ne dit rien de son avancement.** C'est ce qui rend les deux niveaux
indépendants.

### 3. Un statut unique, quatre états

`en cours` / `réussi` / `terminé avec des échecs` / `échoué` — **même sémantique sur tout id**,
maître comme vidéo. Une seule chose à suivre.

- `terminé avec des échecs` sur un maître : le parcours est allé au bout, une partie des vidéos
  n'a pas abouti. Sur une chaîne réelle c'est le cas **normal**, pas l'exception.
- `échoué` sur un maître : **le travail du maître** a échoué — URL invalide, chaîne inexistante,
  énumération impossible. Aucune vidéo n'est en cause.

Un statut binaire avait été écarté pour une raison précise : une vidéo morte qui ne basculerait
jamais empêcherait le maître de terminer, et l'appelant interrogerait indéfiniment.

### 4. Webhook optionnel, déclencheur choisi dans la requête

La requête porte l'URL **et** ce dont on veut être rappelé : **à chaque vidéo prête**, **à l'état
terminal du maître**, ou **les deux**.

Pour une vidéo seule, les deux déclencheurs tombent au même instant : le choix n'a de sens que
sur une chaîne.

### 5. Le webhook est rejoué jusqu'au HTTP 200

Backoff **1, 2, 4, 8, … jusqu'à 256 minutes** — soit **8 h 31 de tentatives sur 9 appels**.

Conséquence assumée : il faut une **file de notifications persistante** dans le module. Le webhook
n'est pas un confort, il porte une garantie.

### 6. Trois couches, à ne pas mélanger

| Couche | Ce qu'elle fait |
|---|---|
| **Réception** | le travail est **stocké**, rien n'est traité ; le retour porte un **id de transaction** |
| **Traitement** | des workers prennent le travail **dans l'ordre d'arrivée** ; le **nombre de workers par source** (youtube, instagram, tiktok) est un **paramètre de l'application** ; le claim porte un **statut et une heure** ; une sécurité fait passer en erreur si le traitement plante ; le résultat va dans une **table partitionnée à la journée**, avec une **rétention paramétrée en jours** |
| **Restitution** | se déclenche quand le résultat est stocké ; joue le webhook s'il y en a un |

**La sécurité anti-plantage ne peut pas être le process lui-même** — un process qui plante ne met
pas son propre statut à jour. C'est **l'heure de prise** qui le permet : un veilleur repère les
travaux pris depuis trop longtemps et tranche.

### 7. La consommation est une lecture simple

**Aucun flag de consommation.** La donnée est disponible **le temps du stockage**, relisable
autant de fois qu'on veut. Deux conséquences :

- un consommateur idempotent peut rejouer sans précaution ;
- un résultat que personne ne vient chercher **expire en silence** — rien ne distingue « consommé »
  de « jamais consommé ». Le webhook le détecte, puisqu'il n'obtiendra jamais son 200 — mais
  seulement si l'appelant en a posé un.

### 8. Deux surfaces : MCP et REST

La soumission et la consommation existent **en MCP et en API REST**.

### 9. docflow sort du flux de livraison

Le résultat vit dans le service jusqu'à ce que l'appelant vienne le chercher. Le module ne dépose
plus rien.

Tombent : le worker de dépôt, le mapping des métadonnées, l'identité machine propre, la « double
posture MCP » backend + client, `get_corpus` et ses curseurs par appelant.

Et **un invariant s'inverse** : la règle V2 était « la stack ne proxifie **jamais** le contenu des
transcripts ». Désormais c'est elle qui le restitue. C'était une frontière de données explicite —
son renversement est délibéré.

### 10. MinIO tombe, et le cycle d'upload avec

Plus de `corpus-audio`, plus de `corpus-transcripts`, plus de slots présignés. Les quatre tools
d'upload (`create_upload_request`, `request_upload_slot`, `finalize_upload`,
`close_upload_request`) disparaissent.

### 11. Hébergement : VM dédiée, Docker du host en SSH

Le service tourne sur une **VM dédiée** du projet devpod et lance les conteneurs sur le **Docker
du host** de cette VM.

**Pas de mTLS : connexion SSH** — `DOCKER_HOST=ssh://<user>@<host>`, supporté nativement par le
CLI Docker. L'image backend a donc besoin de `docker-ce-cli` **et** `openssh-client`.

- ~~Les conteneurs lancés doivent recevoir **`--network <projet>_default`**, sinon ils ne résolvent
  pas la base.~~ **Amendé (2026-10-10, lot "relais audio volume local")** : l'option a été
  retirée pour les **scrapers**. Depuis que l'audio passe par un volume monté et non plus par
  MinIO, un scraper n'appelle plus aucun service interne — son env ne porte que `LOG_LEVEL` et
  les cookies, et le bridge par défaut lui suffit pour joindre Internet. Lui donner le réseau du
  projet lui ouvrirait la base et MinIO sans aucun besoin. La règle reste valable pour un
  conteneur qui, lui, aurait besoin de résoudre un service du projet.
- Une entrée **`known_hosts`** doit être provisionnée : sans elle, soit la connexion échoue, soit
  on désactive la vérification d'hôte et le dispositif perd son intérêt.
- À savoir, sans que ça remette la décision en cause : **SSH au lieu de mTLS change le type de
  justificatif, pas le niveau de privilège.** Qui peut lancer `docker` sur un host peut y devenir
  root. Le gain réel de SSH est une **clé révocable** et des **journaux d'accès** — ce que le
  socket monté ne donne pas.

### 12. La clé SSH est un secret système posé dans l'application

Elle est lue **sans personne devant l'écran** — un worker réclame un job à 3 h du matin. C'est
donc un secret **système**, pas un secret d'utilisateur : un secret d'utilisateur employé par un
traitement de fond échoue la nuit, sans témoin.

Or le magasin de l'application est aujourd'hui **intégralement scopé utilisateur** —
`user_wallets(user_id)`, `user_secrets(user_id, …)`, `read_secret_by_id(secret_id, user_id, …)`.
Il faut donc **ouvrir une portée système** : secrets d'infrastructure sans `user_id`.

- posés par un **administrateur** seulement — cette clé donne de fait root sur le host ;
- **en écriture seule** : on remplace, on ne relit jamais ;
- jamais dans l'image, ni dans une couche, ni dans `docker inspect`, ni dans un journal ;
- à l'usage, `ssh -i` veut un fichier : même motif que l'`env_file()` 0600 déjà en place.

### 13. L'audio passe par un volume mappé sur un chemin local du host

Le conteneur scraper écrit l'audio dans un **volume mappé vers un chemin local** du host de la VM
dédiée. C'est le relais entre le téléchargement et l'envoi en transcription.

Ça **simplifie** les scrapers au lieu de les compliquer : `download.py` télécharge déjà dans un
`local_path` avant d'appeler `minio_uploader.upload_audio()`. Retirer MinIO retire l'étape
d'upload.

### 14. La transcription est TOUJOURS un service distant, choisi par l'utilisateur

**Whisper n'est jamais sur la machine.** Le conteneur récupère l'audio, le pose sur le volume,
puis l'audio est poussé vers un **service distant**. Toujours. Et c'est **l'utilisateur, dans son
paramétrage, qui choisit le service**.

Pourquoi c'était possible : le GPU n'apportait **ni qualité ni vitesse**. C'est le même modèle
`large-v3` des deux côtés, et le local est plus *lent* (10-20 min contre 30 s pour 5 min d'audio
en SaaS). Le GPU n'était là que pour ne pas payer — `docs/specs/04-transcription.md` l'écrit :
« Coût : 0$ (juste l'électricité du GPU) ».

**Amendement du 2026-10-10 : le provider n'est PAS retiré.** Son code reste dans le worker ; il
n'est simplement pas utilisable sur une VM dédiée sans GPU (`large-v3` sur 4 vCPU transcrit plus
lentement que le temps réel). Ce qui tombe en pratique est la **dépendance** à pve2 dans le flux :
l'audio passe par un volume local (décision 13), qui n'atteint pas une autre machine.

⚠️ Si faster-whisper devait un jour tourner ailleurs que sur la VM dédiée, **la tension A se
rouvre** : un volume monté sur un host est invisible depuis un autre. C'est précisément ce que
MinIO franchissait.

**Effet de bord favorable : le garde-fou de coût revient.** Toute transcription est payante, et
c'est la **clé de l'utilisateur** qui paie. Le quota et le crédit de cet utilisateur deviennent
donc la limite naturelle — le dispositif `user_transcription_keys` / wallets / `credit_monitor`
existant cesse d'être accessoire et devient central.

Ordre de grandeur, pour mémoire : une chaîne de trois cents vidéos d'une heure coûte **~108 $**
chez OpenAI Whisper, **~78 $** chez Deepgram.

---

## Tensions à lever avant de coder

### A. ~~Le relais de l'audio~~ — **tranchée** (décision 13)

Volume mappé vers un chemin local du host. Et la décision 14 fait disparaître la frontière entre
machines qui rendait ce relais difficile : plus de worker GPU sur pve2 à alimenter.

### B. ~~Le bloc `output` du contrat scraper~~ — **tranchée** (décision 15)

Le champ `type` est **supprimé**. Il n'avait qu'une valeur (`"minio"`), personne ne le validait,
personne ne branchait dessus : il donnait l'illusion d'un point d'extension sans en être un.

La garantie que le dispatch devait apporter est obtenue autrement : le scraper **valide son
entrée à l'arrivée** et émet un event `error` explicite si `output` n'a pas la forme attendue.
Sans ça, un backend neuf face à une image périmée meurt sur `KeyError: 'endpoint'` dans un
uploader MinIO — on débogue au mauvais endroit alors que la cause est un écart de version
(`SCRAPER_IMAGE_TAG` permet d'épingler les scrapers à un tag différent du backend).

### 15. Le contrat scraper : `output` perd son `type`, l'audio reste sur place

Le changement est une **suppression**, pas une réécriture :

| Fichier | Ce qui change |
|---|---|
| `download.py` | `local_path` pointe dans le répertoire monté ; l'upload disparaît ; **on cesse de supprimer le fichier** ; l'event émet `audio_path` au lieu de `audio_s3_key` |
| `minio_uploader.py` | **supprimé** (45 lignes) |
| `base/requirements.txt` | `minio>=7.2` retiré — allège les **trois** images |
| `scraper_orchestrator._build_payload` | nouveau bloc `output`, et le consommateur d'events lit le nouveau champ |
| `docs/specs/03-scrapers.md` | révisé **dans le même changement** — le contrat y est spécifié ligne 69 (`output`) et ligne 88 (`item_done`) |

`audio_s3_key` est **renommé** `audio_path`, pas réutilisé : un champ nommé `s3_key` contenant un
chemin de fichier induirait en erreur pendant des années.

Trois constats ont rendu ce changement bien plus petit qu'annoncé :

- **instagram et tiktok sont des stubs** (31 et 26 lignes d'`entrypoint`, aucune logique de
  téléchargement) : seul le scraper youtube a du vrai code à modifier ;
- `_tmp_dir()` renvoie déjà `tempfile.gettempdir()` et son docstring le dit « overridable » : le
  scraper **écrivait déjà** dans un chemin local ;
- `minio` est dans l'image de **base**, donc son retrait profite aux trois.

Au passage, la spec 03 était déjà en retard : son `prefix` documenté est
`"{tenant_id}/{role_id}/{source_id}/"` avec un `role_id` retiré par la migration 0011, alors que
le code construit `{tenant_id}/v2/{source_id}/`.

---

## Tensions à lever avant de coder

### D. Personne ne nettoie les fichiers audio

MinIO avait un `keep_audio` ; un répertoire monté n'a **aucun cycle de vie**. La rétention
paramétrée porte sur la **table de résultat partitionnée**, pas sur les fichiers.

Une chaîne de trois cents vidéos représente plusieurs dizaines de Go d'audio sur le disque d'une
VM dédiée. Il faut dire **qui supprime et quand**, et prévoir le cas **disque plein** — qui arrête
tout sans prévenir.

**Cette tension n'est plus reportable** : c'est la ligne `local_path.unlink(missing_ok=True)` de
`download.py` qui empêchait aujourd'hui le disque de se remplir, et la décision 15 la retire. La
question « qui supprime l'audio » fait donc partie de ce changement, pas d'un suivant.

Un piège qui va avec, et qui ne se voit qu'à l'exécution : **les droits sur le montage**. Le
scraper écrit avec l'utilisateur de son conteneur ; ce qui pousse l'audio vers le service distant
doit pouvoir le **lire**.

### C. Simplification, ou nouveau module ?

**Question de contrôle posée et non encore tranchée.** L'objectif de départ — simplifier — est
atteint. Mais le chemin a emporté docflow, MinIO, le cycle d'upload, la sélection, et ajouté une
VM dédiée, un accès SSH, une portée de secrets système et une double surface.

- **une simplification** → on fait évoluer le code existant : migrations additives, contrat révisé,
  retrait progressif ;
- **un nouveau module** → base propre, et suppression en masse de l'existant.

La réponse change tout ce qui vient ensuite, y compris le sort des trois epics du backlog actuel.

---

## Restent ouverts

| Sujet | Pourquoi ça compte |
|---|---|
| **L'ordre d'arrivée face à une chaîne de 300 vidéos** | posé deux fois, non tranché. Si les 300 entrent dans la file à l'arrivée, une vidéo soumise une minute après attend des heures. Décide aussi de la forme de la table de travail : 300 lignes d'un coup, ou un maître qui engendre au fil de l'eau |
| **Durée de rétention** | elle doit couvrir l'horizon de rappel (8 h 31) : un appelant indisponible une journée perdrait **définitivement** un résultat jamais déposé ailleurs |
| **Le palier de 256 min** | on s'arrête après, ou on y reste indéfiniment ? Décide si un appelant mort fait accumuler du travail à notifier sans fin |
| **Le veilleur** | après combien de temps un travail pris est-il déclaré mort, et le rejoue-t-on ou l'échoue-t-on ? |
| **MCP et REST** | le même contrat exposé deux fois, ou deux surfaces distinctes ? Deux contrats à publier, deux modèles d'authentification |
| **Le pooling polymorphe** | une seule API qui rend deux formes selon la nature de l'id est une source classique de bugs côté client : champ discriminant, ou deux routes ? |
| **Le repli quand l'utilisateur n'a pas de clé** | toute transcription est payante depuis la décision 14. Le pool `shared_default` existait avec des clés admin — « pas de clés user = pas de coût ». Qui paie désormais : personne (pas de clé = pas de service), ou l'administrateur ? |
| **Ce que contient le résultat** | texte brut, JSON pivot, segments horodatés ? C'est ce que l'appelant consomme, donc le cœur du contrat |

## Ce que ce cadrage ne décide pas

Il ne décide rien sur le **frontend** (toujours « en sursis »), ni sur les **bugs ouverts** de
l'audit du 2026-07-05 — BUG-01 et BUG-02 restent bloquants sur le pipeline actuel, et leur sort
dépend de la tension C.
