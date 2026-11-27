# Kohaliku ETL-redaktori reeglid

Kohalik redaktor kirjutab ainult valitud GeoPackage’i tööruumi. EGT Portali
varasem Faktika redaktor oli reeglite võrdlusmaterjal; Portali kihi, tabeli ega
redigeerimise õigusi ei kasutata. Ühenduse loomine pole vajalik.

| Teema | Varasem Faktika redaktor | Kohalik ETL-redaktor |
| --- | --- | --- |
| Koodiväljad | REST-domeenid, vajadusel alamtüübi kaupa. | Valikloendid nelja ETL-malli lehtedelt `Väljad` ja `Klassifikaatorid`. Näitab nimetust ja salvestab uue valiku koodina. Muutmata algväärtus säilib, ka kui domeen seda ei tunne. |
| Sõltuvad väljad | Kihistik sõltus indeksist. Genees kehtis pinnakattele, litoloogia täiend aluspõhjale. Liitüksusel olid eraldi ülemine ja alumine indeks ning kihistik. | Samad reeglid kehtivad kohaliku geoloogilise kirjelduse igal real. Kihistikud leitakse valitud indeksi koodihierarhiast kaasasolevate ETL10 klassifikaatorite põhjal. Liitüksuse kummalgi indeksil on oma kihistikuvalik; teist liitüksust alamindeksiks valida ei saa. Mittekohalduvad lahtrid on kirjutuskaitstud ja nende olemasolevaid väärtusi ei kustutata. |
| Järgmine kiht | Eelmise alumisest piirist sai uue ülemine piir. Uuele reale võeti kaasa üksus, autor ja alus. | „Lisa järgmine kiht” kasutab samu lähteväärtusi; need jäävad muudetavaks. |
| Sügavus ja kõrgus | Paksus arvutati sügavuste vahena; absoluutpiirid nullpunkti kõrgusest ja suhtsügavustest. | Arvutus tehakse kasutaja käsul. Absoluutpiir eeldab ühist vertikaalset nullpunkti; kõrgussüsteemi automaatselt ei teisendata ja mõõdetud kogusügavust ei kirjutata üle. |
| Valideerimine | Salvestamiseks nõuti kohustuslikke metainfo välju, sobivaid koordinaate, kasvavaid mittekattuvaid sügavusi, õiget üksuste järjekorda ja liitüksuse täielikkust. | Kohalik kirje võib jääda poolikuks. Ekspordieelne kontroll blokeerib kattuvad ja vigased geoloogilised sügavusvahemikud ning puuduvad või sobimatud liitüksuse komponendid. Hoiatuste korral võib eksportida mustandi. See ei asenda EGT-laaduri kontrolli. |
