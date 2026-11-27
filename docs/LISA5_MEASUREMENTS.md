# Lisa 5 aluskorra mõõteandmete import

Vali **Kohalikud andmed → Litotulp… → Lisa 5 – aluskord → Impordi
mõõteandmed…**. Exceli töövihikus kasuta üht lehte nimega `Mõõteandmed`
või `Measurements`. CSV/TSV fail peab olema UTF-8 kodeeringus. CSV võib
kasutada koma või semikoolonit; komaga kümnendite jaoks on mugavam
semikoolon või tabeldus. Exceli valemite asemel impordi väärtused.

**Impordi mõõteandmed…** kõrval olev nupp **Exceli näidis…** salvestab
kaasasoleva näidisfaili koopia. Enne pärisandmete importi asenda
sünteetilised näidisread enda mõõtmistega.

| Veerg | Mida sisestada |
| --- | --- |
| `rada` | `density_probe`, `density_sample`, `magnetic`, `structures` või `migmatization` |
| `sügavus_m` | Mõõtesügavus meetrites, litotulbaga samast nullpunktist. Kõrgusi, koordinaate ega kaldpuuraugu sügavusi automaatselt ei teisendata. |
| `väärtus` | Positiivne tihedus, märgiga magnetiline vastuvõtlikkus või struktuurinurk 0–90°. Sonditiheduse tühi väärtus katkestab joone sellel sügavusel. |
| `ühik` | Tihedus: `g/cm³` või `kg/m³`. Vastuvõtlikkus: `SI`, `mSI` (10⁻³ SI) või `µSI`. Nurk on kraadides. |
| `tüüp` | Struktuuri puhul `gneisilisus`, `lõhe` või `muu`; migmatiseerumise puhul aste (vt allpool). |
| `asimuut_deg` | Ainult struktuurireal ja valikuline. Märgi saba suund algab 0° juures üles ja kasvab päripäeva; tühja väärtuse korral kuvatakse ainult punkt. |
| `lõpp_m` | Migmatiseerumise vahemiku alumine sügavus meetrites, suurem kui `sügavus_m`. Teiste radade ridadel jäta see tühjaks. |

Ingliskeelsed veerud: `track,depth_m,value,unit,type,azimuth_deg,end_m`.

Sonditihedus joonistub kõverana ning proovitihedus ja magnetiline
vastuvõtlikkus horisontaalsete ribadena. Tiheduse mõlemad rajad kasutavad
ühist telge g/cm³; magnetiline vastuvõtlikkus on joonisel mSI-des.
Teljed laienevad, kui mõõtmised väljuvad näidise vahemikust. Struktuuri
sügavus määrab punkti kõrguse ja struktuurinurk asukoha 0–90° teljel.
Asimuut on eraldi mõõde, mitte kalde teisendus.

## Migmatiseerumise aste

Vali rajaks `migmatization` (sobib ka `migmatiseerumine`). Vahemiku algus
on `sügavus_m`, lõpp `lõpp_m` ning aste `tüüp`. Selles reas jäta ühik
ja asimuut tühjaks. Lubatud astmed on `migmatiseerumata`, `nõrgalt
migmatiseerunud`, `keskmiselt migmatiseerunud` ja `tugevalt
migmatiseerunud` (ingliskeelsed võtmed `none`, `weak`, `moderate`,
`strong`). Näiteks ainult migmatiseerumisega CSV:

```csv
rada;sügavus_m;lõpp_m;tüüp
migmatization;428;436,4;migmatiseerumata
migmatization;436,4;447;nõrgalt migmatiseerunud
migmatization;449;470;keskmiselt migmatiseerunud
migmatization;470;500,6;tugevalt migmatiseerunud
```

Vahemikud võivad puutuda, kuid ei tohi kattuda. Näites jääb 447–449 m
migmatiseerumise aste määramata: seal kuvatakse tavaline kivimimuster,
mitte „migmatiseerumata”. Viirutuseks peavad olema sisse lülitatud
**Migmatiseerumise aste** ja **Mustrid**. Kivimitulba värv ja kihipiirid
jäävad alles ka siis, kui mõõdetud vahemik ületab kihipiiri.

Failis olev rada asendab sama rada eelvaates; teised rajad jäävad alles.
**Salvesta objekti juurde** kinnitab muudatused kohalikku GeoPackage’i.
**Eemalda mõõteandmed** eemaldab rajad eelvaatest; püsivaks eemaldamiseks
vajuta seejärel salvestusnuppu. Linnuke mõjutab ainult kuvamist.
Impordifaili, salvestatud originaali ja EGT andmebaasi ei muudeta.
