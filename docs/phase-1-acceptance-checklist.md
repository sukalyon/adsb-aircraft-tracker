# Phase 1 Acceptance Checklist

## Amaç

Faz 1 sonunda canlı veri hattısının temel davranışlarını UI bağımsız doğrulamak.

## Kabul Kriterleri

- decoder snapshot kaynağı adapter üzerinden okunabiliyor
- geçersiz aircraft kayıtları sayılıyor ve düşürülüyor
- ham kayıtlar kanonik `RawAircraftMessage` modeline dönüştürülüyor
- normalize telemetry beklenen fixture ile eşleşiyor
- `aircraft_id` ile state merge çalışıyor
- parsiyel update önceki geçerli pozisyonu koruyor
- out-of-order update state'i geriye sarmıyor
- trail bounded tutuluyor
- stale cleanup aktif track'i temizliyor
- debug raporu snapshot bazında toplamları ve aktif aircraft listesini üretiyor

## Mevcut Doğrulama Yüzeyleri

- `python3 -m unittest discover -s backend/tests -v`
- `python3 scripts/debug_state_view.py --snapshot samples/fixtures/readsb/basic_snapshot.json`

## Faz 1 Sonu Checkpoint

- Ne tamamlandı: source contract, veri modelleri, readsb file adapter, normalization pipeline, in-memory state store, debug raporu ve testler
- Ne kaldı: gerçek decoder entegrasyonunda canlı snapshot kaynağı, WebSocket dağıtımı, 2D istemci
- Mimari kararlar: `readsb` JSON snapshot başlangıç kaynağı, Python backend çekirdeği, `aircraft_id` tabanlı merge, domain ve render state ayrımı
- Teknik borçlar: HTTP polling adapter yok, config sistemi yok, runtime logging ve metrics henüz yok
