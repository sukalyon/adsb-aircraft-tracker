# Phase 1 Source Contract

## Amaç

Faz 1 içinde decoder çıktısını backend çekirdeğine hangi sınırdan alacağımızı ve bunun repo içinde nasıl temsil edileceğini sabitlemek.

## Kapsam

Bu proje:

- ADS-B / Mode-S decoder çıktısını tüketir
- gelen veriyi normalize eder
- canlı aircraft state üretir
- daha sonra bunu istemcilere yayınlar

Bu proje:

- kendi RF decoder’ını yazmaz
- SDR sinyal işleme katmanını yeniden implement etmez

## Varsayılan Decoder Yönü

İlk uygulama yönü `readsb` üstünden alınan JSON aircraft verisidir.

Neden:

- sıcak başlangıç için düşük entegrasyon maliyeti
- test fixture üretmeye uygun olması
- adapter sınırı kurulduğunda başka decoder’lara taşınabilir olması

İkincil destek hedefi:

- `dump1090-fa` benzeri JSON çıktılar için adapter uyumu

## Canonical Input Boundary

MVP için canonical source boundary:

- kaynak: decoder tarafından üretilen JSON aircraft listesi
- taşıma biçimi: dosya okuma, HTTP polling veya yerel endpoint fark etmeksizin adapter arkasında soyutlanır
- ingestion katmanının dışarı verdiği yapı: `RawAircraftMessage`

İlk sürümde backend geri kalan katmanları yalnızca şu garantiye güvenir:

1. her ham kayıt bir capture timestamp içerir
2. aircraft kimliği mümkün olduğunda `aircraft_id` olarak normalize edilir
3. eksik alanlar ham modelde korunur, normalize modelde temizlenir
4. decoder’a özel alanlar çekirdek state modeline sızdırılmaz

## Katman Sınırları

### 1. Ingestion

Sorumluluk:

- decoder çıktısını almak
- ham kaydı kaynak bilgisi ile sarmalamak
- parse edilebilir kayıtlar üretmek

Çıktı:

- `RawAircraftMessage`

### 2. Normalization

Sorumluluk:

- alan eşleme
- unit standardizasyonu
- invalid/null filtreleme
- canonical telemetry üretimi

Çıktı:

- `AircraftTelemetry`

### 3. State Aggregation

Sorumluluk:

- `aircraft_id` ile merge
- partial update yönetimi
- `last_seen` güncelleme
- bounded trail
- stale cleanup

Çıktı:

- `AircraftState`

### 4. Streaming

Sorumluluk:

- snapshot üretmek
- delta yayınlamak
- istemci kontratını küçük tutmak

Çıktı:

- `AircraftUpdateDTO`

## İlk Repo İskeleti

```text
adsb-aircraft-tracker/
  adsb-aircraft-tracker_project_overview.md
  adsb-aircraft-tracker_execution_plan.md
  adsb-aircraft-tracker_project_log.md
  docs/
  backend/
    app/
      ingestion/
      models/
      state/
      services/
    tests/
  frontend/
    client-2d/
    client-3d-cesium/
  samples/
  scripts/
```

## İlk Teknik Kararlar

### Karar 1

Backend çekirdeği için yön `Python` olacak.

Gerekçe:

- hızlı iteration
- veri işleme ve async servis katmanı için uygunluk
- test ve fixture üretiminin kolaylığı

### Karar 2

Canlı veri hattında domain state ile render state kesin olarak ayrılacak.

Gerekçe:

- backend state ile frontend obje yaşam döngüsü birbirine karışmayacak
- 2D ve 3D istemciler aynı canlı veri kontratını kullanabilecek

### Karar 3

İlk görsel hedef 3D değil, veri hattısını doğrulayan 2D istemci olacak.

Gerekçe:

- telemetry ve state hatalarını render karmaşıklığından ayırmak

## Task 1 Teslim Kriteri

Bu task tamamlanmış sayılırsa:

- plan kök dizinde kayıtlıdır
- source contract yazılıdır
- proje günlüğü başlatılmıştır
- klasör iskeleti oluşturulmuştur

## Task 1 Sonu Kontrol Sorusu

`Bu task’ı şimdi uygulamak için gerekli dosya/klasör/karar elimizde var mı?`

Cevap: Evet.

Eksik kalanlar ama task’ı bloklamayanlar:

- gerçek decoder örnek JSON dosyası
- fixture için alan varyasyonları
- stale timeout ve trail limit varsayılan değerleri
