# Cloudflare TLS — Gems POS (Full strict)

ဒီ guide က Cloudflare proxy နဲ့ HTTPS သုံးရန် ဖြစ်ပါတယ်။ Default installer က HTTP IP access အတိုင်း ဆက်ရှိပါတယ်။ `your-domain.com` နဲ့ `YOUR_VPS_IP` ကို သင့် domain/public IP နဲ့ အစားထိုးပါ။

Cloudflare ရဲ့ browser-facing certificate နဲ့ VPS ရဲ့ origin certificate နှစ်ခုလိုပါတယ်။ ဒီနည်းက VPS မှာ Let's Encrypt certificate ကိုသုံးပြီး Cloudflare ကို **Full (strict)** ထားပါတယ်။ Cloudflare API token ထည့်ရန် မလိုပါ။

## 1. Cloudflare nameservers / DNS

Cloudflare မှာ domain ထည့်ပြီး Cloudflare ပေးတဲ့ nameservers ကို domain registrar မှာ သတ်မှတ်ပါ။ Cloudflare zone **Active** ဖြစ်ပြီးမှ ဆက်ပါ။ Registrar က Cloudflare မဟုတ်လည်း ရပါတယ်။

Cloudflare → DNS → Records မှာ:

| Type | Name | Content | Proxy status | TTL |
| --- | --- | --- | --- | --- |
| A | `@` | `YOUR_VPS_IP` | **DNS only** (initial setup) | Auto |

IPv6 origin ကို configure မလုပ်ထားရင် ဒီ hostname ရဲ့ မှားနေတဲ့ AAAA record ကို ဖယ်ပါ။ ဒီ command တွေက apex domain တစ်ခုပဲ configure လုပ်ပါတယ်။ `www` ကို သုံးချင်ရင် DNS နဲ့ origin certificate ထဲ အဲဒီ hostname ကို ထပ်ထည့်ရပါမယ်။

VPS မှာ စစ်ပါ:

```bash
apt-get update
apt-get install -y dnsutils
DOMAIN=your-domain.com
dig @1.1.1.1 "$DOMAIN" A +short
dig @8.8.8.8 "$DOMAIN" A +short
```

DNS only အချိန် result က VPS public IPv4 နဲ့တူရမယ်။

## 2. VPS origin HTTPS ကို အရင်လုပ်ပါ

Gems POS ကို install လုပ်ပြီးသား ဖြစ်ရမယ်။ Vultr Firewall မှာ TCP **80/443** ကို inbound allow လုပ်ပြီး SSH access ကို ထိန်းထားပါ။ Odoo 8070 နဲ့ maintenance 8099 ကို public ဖွင့်ရန် မလိုပါ။

VPS မှာ root နဲ့:

```bash
mkdir -p /root/gems-pos/scripts
curl -fL https://raw.githubusercontent.com/AungKhantPaing5/gems-pos/main/scripts/configure-domain.py -o /root/gems-pos/scripts/configure-domain.py
curl -fL https://raw.githubusercontent.com/AungKhantPaing5/gems-pos/main/scripts/enable-https.sh -o /root/gems-pos/scripts/enable-https.sh
```

Download နှစ်ခုလုံးအောင်မြင်ပြီးမှ သင့် domain/email ပြောင်းပြီး run ပါ:

```bash
bash /root/gems-pos/scripts/enable-https.sh your-domain.com you@example.com
curl -I https://your-domain.com/gems
/snap/bin/certbot renew --dry-run
```

Login redirect 302/303 ရတာလည်း အလုပ်လုပ်နေတဲ့ response ဖြစ်နိုင်ပါတယ်။ Script က Let's Encrypt Terms ကို သဘောတူပြီး certificate ထုတ်ပေးပါတယ်။ ရှိပြီးသား domain Nginx site ကြောင့် ရပ်သွားရင် [HTTPS.md](HTTPS.md) ရဲ့ existing-site instructions ကို သုံးပါ။ Data ကို ပြန် initialize မလုပ်ပါနှင့်။

## 3. Cloudflare TLS settings

Origin HTTPS အောင်မြင်ပြီးမှ Cloudflare dashboard မှာ:

1. **SSL/TLS → Overview**: encryption mode ကို **Full (strict)** ရွေးပါ။ Automatic mode selection ရှိရင် custom mode ရွေးပြီး Full (strict) သတ်မှတ်ပါ။
2. **SSL/TLS → Edge Certificates**: Universal SSL certificate က သင့် hostname အတွက် **Active** ဖြစ်တာ စစ်ပါ။ Provisioning ပြီးအောင် စောင့်ရနိုင်ပါတယ်။
3. **DNS → Records**: domain A record ကို **Proxied** (orange cloud) ပြောင်းပါ။
4. **SSL/TLS → Edge Certificates**: **Always Use HTTPS = On** ထားပါ။

Full (strict) က origin certificate ရဲ့ hostname၊ validity နဲ့ trusted issuer ကို စစ်ပါတယ်။ လက်ရှိ installer ရဲ့ domain HTTP→HTTPS redirect နဲ့ Flexible mode ကို တွဲမသုံးပါနှင့်; redirect loop ဖြစ်နိုင်ပါတယ်။

ပြီးရင် `https://your-domain.com/gems` နဲ့ ဝင်ပါ။ Proxy ဖွင့်ပြီးနောက် DNS query က Cloudflare IP တွေထွက်တာ ပုံမှန် ဖြစ်ပါတယ်။

## 4. POS cache / Backup & Restore

Login, sales နဲ့ stock pages တွေကို **Cache Everything** rule မပေးပါနှင့်။ Cloudflare → Caching → Cache Rules မှာ သင့် POS hostname အတွက် **Bypass cache** rule ထားနိုင်ပါတယ်။ Existing broad cache rules ရှိရင် POS rule က effective ဖြစ်တာ စစ်ပါ။ Application authentication ကို ဆက်သုံးပါ။

Cloudflare proxied uploads မှာ သင့် plan ရဲ့ request-body size limit နဲ့ timeout limit ရှိပါတယ်။ Nginx maintenance config က 1 GB လက်ခံနိုင်သော်လည်း Cloudflare က အဲဒီအရွယ်အစားကို လက်ခံနိုင်တယ်လို့ မဆိုလိုပါ။ Large backup restore ကို VPS ပေါ်က CLI နဲ့လုပ်ပါ:

```bash
bash /root/gems-pos/scripts/restore-ui.sh /path/to/ACTUAL_BACKUP.tar.gz /root/gems-pos --replace-existing
```

ဒီ command က live database ကို replace လုပ်ပါတယ်။ Restore လိုအပ်မှသာ၊ မှန်တဲ့ backup archive နဲ့သာ သုံးပါ။ Normal TLS setup အတွက် run ရန် မလိုပါ။

## 5. Verify and renewal

VPS မှာ:

```bash
nginx -t
curl -I https://your-domain.com/gems
/snap/bin/certbot certificates
/snap/bin/certbot renew --dry-run
systemctl list-timers --all | grep -E 'certbot|snap.certbot'
```

Browser မှာ admin/staff login၊ sale နဲ့ stock refresh ကို စမ်းပါ။ Cloudflare proxy ဖွင့်ပြီးနောက် `renew --dry-run` ကိုလည်း စစ်ပါ။ HTTP-01 renewal အတွက် port 80 နဲ့ `/.well-known/acme-challenge/` path ကို Cloudflare rules/WAF က block သို့မဟုတ် login/challenge မလုပ်ရပါ။ လိုအပ်ရင် သက်ဆိုင်ရာ rule ကို ပြင်ပါ။ TLS setup command ကို နေ့တိုင်း run ရန် မလိုပါ; Certbot renewal schedule ကို အသုံးပြုပါတယ်။

Apt Certbot သုံးထားရင် `/snap/bin/certbot` အစား `certbot` ကို သုံးပါ။ IP HTTP site က ဆက်ရှိပါတယ်; orange cloud တင်ခြင်းက direct VPS IP access ကို firewall မှာ အလိုအလျောက် ပိတ်မပေးပါ။

## Errors

| Error | Check |
| --- | --- |
| 521 / 522 | Nginx running ဖြစ်လား၊ origin IP မှန်လား၊ TCP 443 ကို cloud/local firewall မှာ allow လား |
| 525 | Origin TLS handshake/configuration နဲ့ Nginx logs |
| 526 | Certificate expiry၊ hostname match နဲ့ trusted issuer; Full (strict) အတွက် valid origin certificate လို |
| Too many redirects | Flexible အစား Full (strict) သုံးထားလား၊ conflicting redirect rules ရှိလား |
| NXDOMAIN during issue | Nameserver/hostname/A record မှန်ပြီး DNS ready ဖြစ်လား |
| Renewal fails after proxy | Port 80/ACME path/WAF/cache/redirect rules |

ဒီ guide က **Let's Encrypt origin + Cloudflare Full (strict)** ကို configure လုပ်ပါတယ်။ Cloudflare Origin CA certificate ရှိပြီးသားဆို Full (strict) မှာ သုံးနိုင်ပါတယ်။ Origin CA certificate သီးသန့်က browser တွေ တိုက်ရိုက် trust မလုပ်တာကြောင့် DNS only ပြောင်းပြီး origin ကို တိုက်ရိုက်ကြည့်လျှင် certificate warning ဖြစ်နိုင်ပါတယ်။ Origin CA သုံးဖို့ ဒီနည်းမှာ မလိုပါ။

Official references:
- [Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/)
- [Universal SSL](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/enable-universal-ssl/)
- [Always Use HTTPS](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/always-use-https/)
- [Cloudflare upload limits](https://developers.cloudflare.com/network/maximum-upload-size/)
- [Origin CA](https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/)
