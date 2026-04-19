# Data Model Contract

## Amaç

Bu belge, Faz 1 içinde kullanılacak kanonik veri modellerini ve alan kurallarını sabitler.

## Model Sınırları

### `RawAircraftMessage`

Amaç:

- decoder çıktısından gelen tek aircraft kaydını, kaynak bilgisiyle birlikte saklamak

Kurallar:

- `aircraft_id` ham kayıttan çıkarılan en erken güvenilir kimliktir
- `captured_at` UTC timestamp olmalıdır
- raw alanlar opsiyoneldir; eksik veri normaldir
- decoder’a özgü tam payload `raw_payload` içinde korunur

Alanlar:

- `source`
- `decoder_type`
- `captured_at`
- `aircraft_id`
- `raw_callsign`
- `raw_squawk`
- `raw_category`
- `raw_latitude`
- `raw_longitude`
- `raw_altitude_ft`
- `raw_ground_speed_kt`
- `raw_heading_deg`
- `raw_vertical_rate_fpm`
- `raw_payload`

### `AircraftTelemetry`

Amaç:

- normalization sonrası sistem içinde taşınan kanonik telemetry kaydı

Kurallar:

- `aircraft_id` lowercase olarak tutulur
- `callsign` trimlenmiş metindir
- irtifa `ft`, hız `kt`, dikey hız `fpm`, yön `deg` olarak tutulur
- position alanları parsiyel update senaryosu yüzünden opsiyoneldir

Alanlar:

- `aircraft_id`
- `captured_at`
- `source`
- `callsign`
- `squawk`
- `category`
- `latitude`
- `longitude`
- `altitude_ft`
- `ground_speed_kt`
- `heading_deg`
- `vertical_rate_fpm`

### `AircraftState`

Amaç:

- sistemin aktif aircraft başına tuttuğu canlı birleşik durum

Kurallar:

- state `aircraft_id` ile tekilleştirilir
- `last_seen` son geçerli telemetry zamanıdır
- `trail` bounded tutulacaktır
- `status` ileride stale cleanup ile güncellenecektir

Alanlar:

- `aircraft_id`
- `last_seen`
- `source`
- `status`
- `callsign`
- `squawk`
- `category`
- `latitude`
- `longitude`
- `altitude_ft`
- `ground_speed_kt`
- `heading_deg`
- `vertical_rate_fpm`
- `trail`

### `AircraftUpdateDTO`

Amaç:

- istemciye gönderilecek kompakt update yükünü temsil etmek

Kurallar:

- yalnızca sıcak path için gerekli alanları taşımalıdır
- event envelope ve snapshot/delta semantiği ayrı katmanda tanımlanacaktır

Alanlar:

- `aircraft_id`
- `updated_at`
- `latitude`
- `longitude`
- `altitude_ft`
- `ground_speed_kt`
- `heading_deg`
- `callsign`

### `AircraftMetadata`

Amaç:

- sıcak path dışında tutulacak enrichment verisini temsil etmek

Alanlar:

- `aircraft_id`
- `registration`
- `manufacturer`
- `model`
- `operator`
- `origin`
- `destination`
- `image_url`
- `country`

## Fixture Seti

Ham fixture dosyaları:

- `samples/fixtures/readsb/basic_snapshot.json`
- `samples/fixtures/readsb/edge_cases_snapshot.json`

Beklenen normalize çıktı fixture dosyası:

- `samples/fixtures/expected/normalized_telemetry_from_basic.json`

## Bu Task İçin Açık Kararlar

- stale timeout değeri henüz sabitlenmedi
- bounded trail limiti henüz sabitlenmedi
- multi-source merge stratejisi ileriki fazda netleştirilecek
