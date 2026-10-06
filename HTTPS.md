# Optional domain + HTTPS setup (Ubuntu 24.04)

ပထမဆုံး README ထဲက one-command installer နဲ့ Gems POS ကို install လုပ်ပါ။ Default က `http://VPS_IP` ဖြစ်ပြီး domain မလိုပါ။ ဒီ guide က domain နဲ့ HTTPS သုံးချင်မှ သီးသန့်လုပ်ရန် ဖြစ်ပါတယ်။ Website data/account တွေကို ပြန် initialize လုပ်ရန် မလိုပါ။

## 1. DNS record

Domain DNS ကို လက်ရှိ authoritative nameserver provider မှာ ပြင်ပါ။ ဥပမာ `payapi.uk` ဆိုလျှင်:

| Type | Name / Host | Value | TTL |
| --- | --- | --- | --- |
| A | `@` | သင့် VPS public IPv4 | Auto / 300 |

`VPS_IP` စာသားကို record ထဲမထည့်ပါနှင့်။ Vultr instance ရဲ့ Public IPv4 ကို ထည့်ပါ။ `payapi.uk.com` မဟုတ်ဘဲ `payapi.uk` ဖြစ်ရမယ်။ Cloudflare သုံးရင် initial certificate ထုတ်နေစဉ် **DNS only** ထားပါ။ ဒီ guide က apex domain တစ်ခုပဲ certificate ထုတ်ပါတယ်။ `www` သုံးချင်ရင် www record နဲ့ certificate ထဲ ထပ်ထည့်ဖို့လိုပါတယ်။

ဒီ hostname အတွက် A record အဟောင်းတွေရှိရင် အခြား VPS ကိုညွှန်နေတဲ့ record ကို ပြင်ပါ။ IPv6 ကို အမှန်တကယ် configure မလုပ်ထားရင် ဒီ hostname ရဲ့ မှားနေတဲ့ AAAA record ကို ဖယ်ပါ။ VPS IP ပြောင်းတဲ့အခါ A record ကိုလည်း ပြောင်းပါ။

VPS မှာ:

```bash
apt-get update
apt-get install -y dnsutils
DOMAIN=payapi.uk
dig @1.1.1.1 "$DOMAIN" A +short
dig @8.8.8.8 "$DOMAIN" A +short
dig @1.1.1.1 "$DOMAIN" AAAA +short
```

A results က သင့် VPS public IPv4 ဖြစ်ရမယ်။ DNS update က cache TTL အပေါ်မူတည်ပြီး စောင့်ရနိုင်ပါတယ်။ `NXDOMAIN` ဖြစ်နေရင် SSL command ကို မပြန်ပြန် run ဘဲ hostname/nameserver/record ကို အရင်ပြင်ပါ။

## 2. Firewall

Vultr Console → သင့် instance နဲ့ချိတ်ထားတဲ့ Firewall Group မှာ inbound TCP **80** နဲ့ **443** ကို internet မှဝင်ခွင့်ပေးပါ။ SSH port ကို ဆက်ခွင့်ပြုထားပါ။ Odoo 8070 နဲ့ maintenance 8099 ကို public ဖွင့်ရန် မလိုပါ။

UFW သုံးထားပြီး active ဖြစ်နေတယ်ဆို:

```bash
ufw status
ufw allow 80/tcp
ufw allow 443/tcp
```

Script က active UFW မှာ port နှစ်ခုဖွင့်ပေးပါတယ်။ Cloud firewall ကိုတော့ Vultr console မှာ လုပ်ရပါမယ်။ HTTP-01 certificate validation အတွက် public port 80 ကို ဝင်လို့ရရမယ်။ Renewal အတွက်လည်း port 80 ကို ဆက်ဖွင့်ထားပါ။

## 3. Download the separate HTTPS helpers

VPS မှာ root နဲ့ run ပါ။ ဒီ command တွေက app/database ကို ပြန် install မလုပ်ပါ။

```bash
mkdir -p /root/gems-pos/scripts
curl -fL https://raw.githubusercontent.com/AungKhantPaing5/gems-pos/main/scripts/configure-domain.py -o /root/gems-pos/scripts/configure-domain.py
curl -fL https://raw.githubusercontent.com/AungKhantPaing5/gems-pos/main/scripts/enable-https.sh -o /root/gems-pos/scripts/enable-https.sh
```

Command နှစ်ခုလုံး download အောင်မြင်ပြီးမှ နောက်အဆင့်ဆက်ပါ။

## 4. HTTPS command

`payapi.uk` နေရာမှာ သင့် domain၊ email နေရာမှာ သင့် email ပြောင်းပါ:

```bash
bash /root/gems-pos/scripts/enable-https.sh payapi.uk you@example.com
```

Script က domain HTTP Nginx site ကို ထည့်ပြီး `nginx -t` စစ်မယ်၊ Certbot မရှိရင် snap နဲ့ install လုပ်မယ်၊ Let's Encrypt certificate ထုတ်ပြီး domain HTTP ကို HTTPS redirect လုပ်ပေးမယ်။ Command run ခြင်းက Let's Encrypt Terms of Service ကို သဘောတူခြင်း ဖြစ်ပါတယ်။ Terms ကို https://letsencrypt.org/repository/ မှာ ကြည့်နိုင်ပါတယ်။ Certbot က certificate renewal schedule ကို install လုပ်ပေးပါတယ်။

အောင်မြင်ရင် `https://payapi.uk` သို့မဟုတ် `https://payapi.uk/gems` နဲ့ဝင်ပါ။ IP HTTP site က ဆက်ရှိနေပါတယ်။ IP address ကို HTTPS certificate ထုတ်ခြင်း ဒီ script မှာ မပါပါ။

Script က `/etc/nginx/sites-available/gems-domain-YOUR_DOMAIN` ကို သုံးပါတယ်။ အခြား site မှာ domain နာမည်ပါပြီးသားဆို overwrite မလုပ်ဘဲ ရပ်ပေးပါတယ်။ Script ကဖန်တီးထားတဲ့ site ကို ထပ် run ရင် Certbot ရဲ့ TLS configuration ကို ထိန်းထားပါတယ်။

## 5. Existing domain site ရှိပြီးသားဆို

ဒီ domain နဲ့ အရင်က Nginx site ရေးပြီးသားဆို ပထမ backup ယူပြီး စစ်ပါ:

```bash
cp -a /etc/nginx "/root/nginx-before-https-$(date +%Y%m%d-%H%M%S)"
nginx -T
```

သင့် domain ရဲ့ server block က Odoo `http://127.0.0.1:8070` ကို proxy လုပ်ထားရမယ်။ Backup/Restore UI အတွက် `/gems-maintenance/` ကို `http://127.0.0.1:8099` သို့ proxy လုပ်ထားရမယ်။ Existing config ထဲ အဲဒါတွေရှိပြီး HTTP domain ဖွင့်လို့ရမှ Certbot ကို တိုက်ရိုက် run ပါ:

```bash
apt-get update
apt-get install -y snapd
systemctl enable --now snapd.socket
```

Certbot ရှိပြီးသားဆို reinstall မလုပ်ပါနှင့်။ မရှိမှ:

```bash
snap install --classic certbot
```

Snap Certbot အတွက် SSL command:

```bash
nginx -t
/snap/bin/certbot --nginx -d payapi.uk --redirect
```

Email နဲ့ Terms prompt ကို ဖြေပါ။ Certbot ကို apt နဲ့ install လုပ်ထားပြီးသားဆို `/snap/bin/certbot` အစား `certbot` ကို သုံးနိုင်ပါတယ်။ Nginx config files တွေကို မသိဘဲ အကုန်ဖျက်ရန် မလိုပါ။

## 6. Verify / renewal

```bash
curl -I https://payapi.uk/gems
/snap/bin/certbot certificates
/snap/bin/certbot renew --dry-run
systemctl list-timers --all | grep -E 'certbot|snap.certbot'
```

Apt Certbot ဆို command path ကို `certbot` ပြောင်းပါ။ Login redirect `302/303` ရတာလည်း app response ဖြစ်နိုင်ပါတယ်။ `renew --dry-run` အောင်မြင်ပြီး renewal timer ရှိတာကို စစ်ပါ။ Script အောင်မြင်တာနဲ့ VPS firewall/DNS/renewal ကို အကုန်စစ်ပြီးသားဟု မဆိုလိုပါ။

## Errors

- **NXDOMAIN**: hostname / DNS nameserver / record မှားနေတယ်။ DNS အရင်ပြင်ပါ။
- **Timeout during connect**: A record IP မှန်လား၊ Vultr firewall / UFW မှာ TCP 80 ဝင်လို့ရလား စစ်ပါ။
- **Wrong server / unauthorized**: A/AAAA records နဲ့ existing Nginx `server_name` စစ်ပါ။
- **502**: `cd /root/gems-pos && docker compose ps` နဲ့ `curl -I http://127.0.0.1:8070/gems` ကို စစ်ပါ။
- Certificate issue fail ဖြစ်ရင် data ကို reset မလုပ်ပါနှင့်။ DNS/firewall ပြင်ပြီး SSL command ကို ပြန် run ပါ။

Official references: [Certbot Nginx instructions](https://certbot.eff.org/instructions?ws=nginx&os=snap), [Let's Encrypt HTTP-01](https://letsencrypt.org/docs/challenge-types/).
