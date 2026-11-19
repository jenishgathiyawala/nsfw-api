# Oracle Cloud (Free) pe deploy karna

Is guide ke end mein ye ho jayega:

```
Laravel ──HTTPS + X-API-Key──▶ https://nsfw.tumhari-site.com ──▶ Caddy ──▶ Docker (NSFW API)
```

Kharcha: **₹0**. Oracle ka "Always Free" server use hoga.

Jo chahiye:
- Ek debit/credit card. Sirf verification ke liye lagta hai, free resources pe charge nahi hota.
- Tumhara domain, jo cPanel pe hai. Usme ek subdomain banayenge, jaise `nsfw.tumhari-site.com`.
- Tumhara Mac, jisme ye project hai.

> Oracle ki website ke button aur menu ke naam kabhi kabhi badal jaate hain. Agar koi naam
> exactly na mile to us jaisa option dhundo.

---

## Step 1: Oracle account banao

1. <https://www.oracle.com/cloud/free/> pe **Start for free** dabao.
2. Email, naam aur country (India) bharo.
3. **Home Region** dhyan se chuno: **India West (Mumbai)** ya **India South (Hyderabad)**.
   Ye baad mein **badal nahi sakta**, aur free server sirf home region mein milta hai.
4. Card details bharo. Ek chhota sa amount hold ho ke wapas aa jata hai.
5. Account banne mein 5–30 minute lag sakte hain. Email aane tak ruko.

---

## Step 2: Server (VM) banao

1. Oracle Cloud console mein login karo.
2. Upar left menu (☰) → **Compute** → **Instances** → **Create instance**.
3. **Name:** `nsfw-api`
4. **Image and shape** → **Edit**:
   - **Image:** **Change image** → **Ubuntu** → **Canonical Ubuntu 24.04** (Minimal wala nahi).
   - **Shape:** **Change shape** → **Ampere** → **VM.Standard.A1.Flex**.
     **2 OCPU** aur **12 GB** memory rakho. Ispe "Always Free-eligible" likha hona chahiye.
5. **Networking:** default rehne do. "Create new virtual cloud network" aur
   **Assign a public IPv4 address = Yes** hona chahiye.
6. **Add SSH keys:** **Generate a key pair for me** chuno, phir
   **Save private key** dabao. Ek `.key` file download hogi. **Ise sambhal ke rakho**, iske
   bina server mein login nahi kar paoge.
7. **Create** dabao. Status 1–2 minute mein **Running** ho jayega.
8. Instance page pe **Public IP address** likha hoga, jaise `140.238.x.x`. Ise copy kar lo.

**"Out of capacity" error aaye to:** free ARM servers kabhi kabhi khatam ho jaate hain.
Networking ke paas **Availability domain** badal ke try karo, ya kuch ghante baad dobara.
Ye common hai, account mein koi galti nahi hai.

---

## Step 3: Port 80 aur 443 kholo (Oracle ki side)

Website ke liye ye do port khulne chahiye.

1. Instance page → **Primary VNIC** section → **Subnet** ke link pe click karo.
2. **Security** (ya **Security Lists**) → **Default Security List** kholo.
3. **Add Ingress Rules** dabao aur ye bharo:
   - Source CIDR: `0.0.0.0/0`
   - IP Protocol: `TCP`
   - Destination Port Range: `80,443`
4. **Add Ingress Rules** dabao.

Port 8000 **mat kholna**. API sirf Caddy ke through bahar jayegi.

---

## Step 4: Mac se server mein login karo

Mac pe Terminal kholo. Download hui key file ka naam apne hisaab se badlo:

```bash
mv ~/Downloads/ssh-key-*.key ~/.ssh/oracle-nsfw.key
chmod 600 ~/.ssh/oracle-nsfw.key
ssh -i ~/.ssh/oracle-nsfw.key ubuntu@<PUBLIC_IP>
```

Pehli baar "Are you sure you want to continue connecting?" puchega. `yes` likho.
Ab tum server ke andar ho. Prompt `ubuntu@nsfw-api:~$` jaisa dikhega.

**Aage ke saare commands server ke andar chalane hain**, jab tak Mac ka naam na likha ho.

---

## Step 5: Server ka firewall kholo

Oracle ke Ubuntu mein ek alag firewall bhi hota hai jo port 80/443 band rakhta hai.
Ye step bhool gaye to site nahi khulegi:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

---

## Step 6: Docker install karo

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```

`exit` ke baad dobara login karo, taaki Docker bina `sudo` ke chale:

```bash
ssh -i ~/.ssh/oracle-nsfw.key ubuntu@<PUBLIC_IP>
docker --version
```

---

## Step 7: Code server pe bhejo (Mac se)

**Mac ke Terminal mein**, project folder ke andar ye chalao:

```bash
cd ~/Downloads/NSFW
git archive --format=tar.gz HEAD | ssh -i ~/.ssh/oracle-nsfw.key ubuntu@<PUBLIC_IP> "mkdir -p nsfw-api && tar -xzf - -C nsfw-api"
```

Isse sirf git mein **commit hui files** jaati hain. Test photos (`dataset/`) git mein
nahi hain, isliye wo server pe nahi jayengi.

---

## Step 8: API key banao aur start karo (server pe)

```bash
cd ~/nsfw-api
echo "API_KEYS=$(openssl rand -hex 32)" > .env
chmod 600 .env
cat .env
```

`cat .env` jo key dikhaye, use copy karke kahin safe rakh lo. Ye Laravel mein lagegi.

Ab API start karo. Pehli baar build hone mein 2–5 minute lagenge:

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/health
```

`"status":"ok"` aaya to API chal rahi hai. Server restart hone pe ye apne aap start ho jayegi.

---

## Step 9: Subdomain banao (cPanel mein)

1. cPanel → **Zone Editor** → apne domain ke aage **+ A Record**.
2. Name: `nsfw` (yaani `nsfw.tumhari-site.com`)
3. Address: Oracle server ka **Public IP**
4. Save.

DNS update hone mein 5 minute se 1 ghanta lag sakta hai. Mac pe check karo:

```bash
ping nsfw.tumhari-site.com
```

Jab ye Oracle wala IP dikhaye, tab aage badho.

---

## Step 10: HTTPS ke liye Caddy lagao (server pe)

Caddy free SSL certificate (Let's Encrypt) khud leta hai aur khud renew bhi karta hai.

```bash
sudo apt install -y caddy
sudo nano /etc/caddy/Caddyfile
```

File mein jo bhi likha hai, sab hata ke sirf ye likho. Domain apna daalo:

```
nsfw.tumhari-site.com {
    reverse_proxy 127.0.0.1:8000
}
```

Save karo: `Ctrl+O`, `Enter`, phir `Ctrl+X`. Uske baad:

```bash
sudo systemctl reload caddy
```

---

## Step 11: Test karo (Mac se)

```bash
curl https://nsfw.tumhari-site.com/health
```

Bina key ke request ka **401** aana chahiye:

```bash
curl -F "file=@photo.jpg" https://nsfw.tumhari-site.com/predict
```

Key ke saath result aana chahiye:

```bash
curl -H "X-API-Key: <TUMHARI_KEY>" -F "file=@photo.jpg" https://nsfw.tumhari-site.com/predict
```

Browser mein `https://nsfw.tumhari-site.com/docs` bhi khulega. Wahan **Authorize** pe key
daal ke photo try kar sakte ho.

---

## Laravel se call karna

Laravel `.env`:

```
NSFW_API_URL=https://nsfw.tumhari-site.com
NSFW_API_KEY=<TUMHARI_KEY>
```

`config/services.php`:

```php
'nsfw' => [
    'url' => env('NSFW_API_URL'),
    'key' => env('NSFW_API_KEY'),
],
```

Call:

```php
use Illuminate\Support\Facades\Http;

$response = Http::withHeaders(['X-API-Key' => config('services.nsfw.key')])
    ->timeout(15)
    ->attach('file', file_get_contents($request->file('photo')->getRealPath()), 'photo.jpg')
    ->post(config('services.nsfw.url') . '/predict');

if ($response->successful() && $response->json('is_nsfw')) {
    // NSFW: upload reject karo
}
```

Key **sirf Laravel ki `.env` mein** rakhni hai. Mobile app ya website ke JavaScript mein kabhi nahi.

---

## Roz ke kaam

Code badla to commit karo, phir **Mac se** dobara bhejo aur server pe rebuild karo:

```bash
cd ~/Downloads/NSFW
git archive --format=tar.gz HEAD | ssh -i ~/.ssh/oracle-nsfw.key ubuntu@<PUBLIC_IP> "tar -xzf - -C nsfw-api"
ssh -i ~/.ssh/oracle-nsfw.key ubuntu@<PUBLIC_IP> "cd nsfw-api && docker compose up -d --build"
```

`.env` (API key) server pe hi rehti hai. Ye command use nahi chhedti.

Server pe kaam ke commands:

| Kaam | Command |
|---|---|
| Logs dekhna | `cd ~/nsfw-api && docker compose logs -f` |
| Restart | `cd ~/nsfw-api && docker compose restart` |
| Band karna | `cd ~/nsfw-api && docker compose down` |
| Key badalna | `.env` edit karo, phir `docker compose up -d` |
| Caddy ke logs | `sudo journalctl -u caddy -f` |

---

## Dhyan rakhne wali baatein

- **Idle server reclaim:** Oracle free account mein agar server 7 din tak bahut kam use ho
  (CPU, network aur memory sab kam), to Oracle use band kar sakta hai. Account ko
  **Pay As You Go** mein upgrade karne se ye band ho jata hai, aur free limit ke andar
  rahoge to tab bhi bill ₹0 aata hai. Upgrade karo to Oracle mein **budget alert** zaroor laga do.
- **Free limit:** total 4 OCPU aur 24 GB RAM ARM pe free hai. Hum 2 OCPU / 12 GB le rahe
  hain, to limit ke andar hain.
- **Server updates:** mahine mein ek baar `sudo apt update && sudo apt upgrade -y` chala do.
- **Key leak ho jaye to:** nayi key banao, `.env` mein `API_KEYS=nayi-key,purani-key` likho
  aur `docker compose up -d` chalao. Laravel mein nayi key daalo, phir purani `.env` se hata do.

## Kuch na chale to

| Dikkat | Kya check karna hai |
|---|---|
| `ssh` pe "Permission denied" | Key path sahi hai? `chmod 600` kiya? User `ubuntu` hai? |
| Site nahi khul rahi / timeout | Step 3 (Security List) aur Step 5 (iptables), dono kiye? |
| Caddy ko certificate nahi mila | `ping` se subdomain Oracle IP dikha raha hai? `sudo journalctl -u caddy` dekho |
| `502 Bad Gateway` | API band hai: `docker compose ps` aur `docker compose logs` |
| Compose bole "Set API_KEYS in .env" | `~/nsfw-api/.env` file bani hai? Step 8 |
| Har request pe `401` | Laravel wali key aur server ki `.env` wali key ek jaisi hain? |
