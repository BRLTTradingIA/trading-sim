# Trading Sim

Robot d'entraînement au trading qui tourne 24 h/24 sur un serveur gratuit.

- Prix en temps réel de Binance (flux à la seconde) pour Bitcoin, Ethereum et l'or (PAXG, 1 jeton = 1 once d'or).
- Analyse du haut vers le bas : tendance 1d et 4h, déclencheur en 1h.
- Trades **simulés** uniquement : aucun compte, aucune clé, aucun ordre réel.
- Stops et objectifs vérifiés à chaque tick de prix.
- Actualités géopolitiques, banques centrales et crypto (flux RSS gratuits), avec pause automatique après une actualité à fort impact.
- Site en direct : prix, trades ouverts, journal de chaque décision, capital, actualités.

## Règles de la stratégie

| Étape | Règle |
|---|---|
| Biais | Acheteur si tendances 1d et 4h haussières, vendeur si les deux baissières, sinon pas de trade |
| Déclencheur 1h | Le RSI repasse au-dessus de 40 après un repli (au-dessous de 60 en vendeur), ou cassure du plus haut / plus bas des 20 dernières bougies |
| Stop | Sous le dernier creux (au-dessus du dernier sommet), entre 1 et 3 ATR |
| Objectifs | 1,5 R : moitié clôturée et stop remonté au prix d'entrée. 3 R : le reste |
| Taille | 1 % du capital risqué par trade, pas d'effet de levier |
| Coûts | 0,1 % de frais par côté + 0,05 % de glissement |
| Sécurités | Un trade max par actif, pas de nouveau trade 60 min après une actu à fort impact, arrêt au-delà de 3 % de perte dans la journée |

Ces règles n'ont pas d'avantage prouvé. Le but de la simulation est justement de le mesurer sur plusieurs semaines. Ce n'est pas un conseil en investissement.

---

## Installation sur un serveur gratuit (Oracle Cloud « Always Free »)

Compter environ une heure la première fois.

### 1. Créer le compte Oracle Cloud

1. Va sur https://www.oracle.com/cloud/free/ et clique sur « Start for free ».
2. Région d'origine (« Home Region ») : choisis une région en Europe, par exemple **Germany Central (Frankfurt)** ou **Netherlands Northwest (Amsterdam)**. Elle ne peut plus être changée ensuite, et Binance bloque les serveurs situés aux États-Unis.
3. Une carte bancaire est demandée pour vérifier ton identité. Tant que tu restes sur les ressources marquées « Always Free », rien n'est prélevé.

### 2. Créer le serveur

1. Menu ☰ → Compute → Instances → « Create instance ».
2. Nom : `tradebot`.
3. Image : **Canonical Ubuntu 22.04** (ou 24.04).
4. Shape : **VM.Standard.E2.1.Micro** (marqué « Always Free-eligible »). Si Oracle propose Ampere A1 en Always Free et qu'il y a de la place, c'est encore mieux.
5. Section « Add SSH keys » : choisis « Generate a key pair for me » et **télécharge la clé privée** (fichier `.key`). Range-la bien : c'est ta seule clé d'accès au serveur.
6. Clique sur « Create ». Au bout de 1 à 2 minutes, note l'**adresse IP publique** affichée.

### 3. Ouvrir le port du site (8080)

1. Sur la page de l'instance, clique sur le lien du **Subnet**, puis sur la **Security List** par défaut.
2. « Add Ingress Rules » :
   - Source CIDR : `0.0.0.0/0`
   - IP Protocol : TCP
   - Destination Port Range : `8080`
3. Enregistre.

### 4. Se connecter au serveur

Sur Windows, ouvre **PowerShell** ; sur Mac, ouvre **Terminal**. Puis (remplace le chemin et l'IP) :

```
ssh -i C:\Users\TON_NOM\Downloads\ssh-key.key ubuntu@IP_DU_SERVEUR
```

Sur Mac/Linux, fais d'abord `chmod 600 ~/Downloads/ssh-key.key`. Réponds `yes` à la première question.

### 5. Installer le robot

Une fois connecté au serveur :

```
sudo apt-get update -y && sudo apt-get install -y git
git clone https://github.com/TON_UTILISATEUR/trading-sim.git
cd trading-sim
cp .env.example .env
nano .env        # mets un mot de passe après DASH_PASSWORD= ; Ctrl+O, Entrée, Ctrl+X
bash deploy/install.sh
```

À la fin, le script affiche l'adresse du site : `http://IP_DU_SERVEUR:8080`. Identifiant : n'importe lequel ; mot de passe : celui du fichier `.env`.

Le robot redémarre tout seul en cas de plantage ou de redémarrage du serveur.

### Commandes utiles (sur le serveur)

| Besoin | Commande |
|---|---|
| Le robot tourne-t-il ? | `sudo systemctl status tradebot` |
| Voir ce qu'il fait en direct | `journalctl -u tradebot -f` (Ctrl+C pour sortir) |
| Redémarrer après un changement de `.env` | `sudo systemctl restart tradebot` |
| Mettre à jour le code | `cd ~/trading-sim && git pull && sudo systemctl restart tradebot` |
| Repartir de zéro (efface tous les trades simulés) | `sudo systemctl stop tradebot && rm -rf ~/trading-sim/data && sudo systemctl start tradebot` |

---

## Tester sur ton ordinateur (facultatif)

Avec Python 3.10+ installé :

```
pip install -r requirements.txt
python -m tradebot.app
```

Puis ouvre http://localhost:8080. Le robot s'arrête quand tu fermes la fenêtre : pour le 24 h/24, il faut le serveur.

## Structure

| Fichier | Rôle |
|---|---|
| `tradebot/market.py` | Historique + flux temps réel Binance, repli automatique toutes les 2 s si le flux tombe |
| `tradebot/strategy.py` | Analyse multi-unités de temps et règles d'entrée |
| `tradebot/broker.py` | Courtier simulé : ouverture, suivi tick par tick, statistiques, sauvegarde dans `data/state.json` |
| `tradebot/news.py` | Actualités RSS, classement par thème et par impact |
| `tradebot/app.py` | Assemble le tout et sert le site |
| `tradebot/static/index.html` | Tableau de bord en direct |
| `tradebot/config.py` | Tous les réglages |
