# Normalization Rules

## Amaç

Ham decoder verisini canlı state store'a gitmeden önce aynı kurallarla temizlemek.

## Kurallar

### Kimlik

- `aircraft_id` lowercase tutulur
- boş kimlik normalize katmanına gelmemelidir

### Timestamp

- tüm zaman damgaları UTC kabul edilir
- `captured_at` her telemetry kaydında korunur

### Callsign / Kod Alanları

- `callsign` trimlenir ve uppercase yapılır
- `squawk` ve `category` trimlenir, uppercase yapılır

### Position

- latitude yalnızca `[-90, 90]` aralığında geçerlidir
- longitude yalnızca `[-180, 180]` aralığında geçerlidir
- tek koordinat eksikse pozisyon geçersiz sayılır ve iki alan da `None` yapılır

### Heading

- derece değeri `0 <= heading < 360` aralığına mod alınarak normalize edilir

### Speed

- negatif hız değerleri geçersiz sayılır ve `None` yapılır

### Altitude / Vertical Rate

- bu aşamada ham integer değerler korunur
- domain seviyesinde daha sıkı kurallar gerekirse state veya analytics katmanında eklenir

## Açık Konular

- altimetre kaynağı seçimi (`alt_baro` vs `alt_geom`) ileride stratejiye bağlanabilir
- multi-source senaryosunda source önceliği henüz tanımlanmadı
