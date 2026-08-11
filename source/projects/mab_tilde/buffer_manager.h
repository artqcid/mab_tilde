// buffer_manager.h -- Buffer~-Tracking für mab~ (nn_tilde-Parität P7)
//
// VORBEREITUNG (Phase-5-Vorbereitung, kein vollständiges Feature):
// Dieser Header ist ein Platzhalter. Die eigentliche Anbindung an das native
// Max-SDK buffer_reference (c74::min::buffer_reference) erfolgt in Phase 5:
//   - `set <attr> <buffer~name>` verlinkt Modell-Buffer-Attribute mit Max-
//     Buffer~-Objekten
//   - `track_buffers <0/1>` aktiviert Buffer-Tracking (Default: 0)
//   - `notify` sendet Buffer-Updates (Länge, SR, Kanalzahl) an Max
//   - Tensor-Attribute (Typ 4) akzeptieren Max-`array`-Namen statt buffer~
//
// WICHTIG: t_symbol wird von ext.h bereitgestellt. Dieser Header muss daher
// NACH ext.h inkludiert werden (mab_tilde.cpp inkludiert ihn nach den
// Max-SDK-Headern). Er selbst inkludiert kein Max-SDK.

#pragma once

// Referenz auf einen Max-Buffer~ (Name + gecachte Metadaten).
struct BufferRef {
    t_symbol* name;      // buffer~-Name (gensym) bzw. interner "attr#idx"-Name
    long channels;       // Kanäle des Buffers
    long frames;         // Frames des Buffers
    float* data;         // Zeiger auf die Buffer-Daten (Sample-Zugriff)
};

// Verwaltet bis zu 16 Modell-Buffer-Attribute.
struct BufferManager {
    BufferRef refs[16];  // P7: Wird in Phase 5 mit nativem Max-SDK buffer_reference verbunden
    long count;          // Anzahl registrierter Buffer-Referenzen
    long track_buffers;  // 1 = Buffer-Tracking aktiv (notify bei Änderungen)
};

// Nullt den BufferManager (im Objekt-Konstruktor aufrufen, z.B. mab_tilde_new).
static inline void buffer_manager_init(BufferManager* bm) {
    if (!bm) return;
    bm->count = 0;
    bm->track_buffers = 0;
    for (long i = 0; i < 16; i++) {
        bm->refs[i].name = nullptr;
        bm->refs[i].channels = 0;
        bm->refs[i].frames = 0;
        bm->refs[i].data = nullptr;
    }
}
