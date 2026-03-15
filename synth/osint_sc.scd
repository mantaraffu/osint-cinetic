// ─────────────────────────────────────────────────────────────────
// OSINT Cinetic — SuperCollider engine
// Avvio: QT_QPA_PLATFORM=offscreen pw-jack sclang synth/osint_sc.scd
// Riceve OSC su porta 9000: /event [freq, amp, reverb, decay_ms, event_code]
// ─────────────────────────────────────────────────────────────────

Server.program = "pw-jack scsynth";
s = Server.default;
s.options.sampleRate        = 48000;
s.options.blockSize         = 1024;
s.options.numInputBusChannels  = 0;
s.options.numOutputBusChannels = 2;
s.options.maxNodes          = 512;
s.options.memSize           = 65536;

s.waitForBoot({

    // ── CAMPANA ETEEREA ─────────────────────────────────────────
    // FM a due coppie portante/modulante con rapporti inarmoni.
    // Decay lungo + FreeVerb ampio → campane quasi continue, distanti.
    SynthDef(\bell, {
        |freq = 220, amp = 0.2, decay = 8.0, pan = 0.0, room = 0.93|
        var env1 = EnvGen.kr(Env.perc(0.08,  decay,       1.0, -4));
        var env2 = EnvGen.kr(Env.perc(0.05,  decay * 0.7, 1.0, -5), doneAction: 2);

        // Indice FM ridotto (1.5 / 0.8) → timbro caldo, non metallico
        var mod1 = SinOsc.ar(freq * 2.756) * (freq * 2.756 * 1.5) * env1;
        var car1 = SinOsc.ar(freq + mod1) * env1 * 0.7;

        var mod2 = SinOsc.ar(freq * 5.404) * (freq * 5.404 * 0.8) * env2;
        var car2 = SinOsc.ar(freq * 2.756 + mod2) * env2 * 0.3;

        var sig = LPF.ar((car1 + car2) * amp, 1200);
        sig = Pan2.ar(sig, pan);
        sig = FreeVerb2.ar(sig[0], sig[1], room, 0.95, 0.35);
        Out.ar(0, Limiter.ar(sig, 0.9));
    }).add;

    // ── SCONTRO ARMATO (190, 191, 192, 193, 196) ───────────────
    // FM percussivo con rumore filtrato.
    // Frequenza medio-alta, decay breve, pan casuale.
    // reverb_mix proporzionale alla distanza (dal fetcher).
    SynthDef(\combat, {
        |freq = 330, amp = 0.5, decay = 2.0, reverb_mix = 0.3, pan = 0.0|
        var env = EnvGen.kr(Env.perc(0.015, decay, 1.0, -5), doneAction: 2);

        // FM index ridotto (2.5) + LPF a 800 Hz → meno metallico
        var mod = SinOsc.ar(freq * 2.8) * (freq * 2.5) * env;
        var sig = SinOsc.ar(freq + mod) * env;

        sig = LPF.ar(sig * amp, 800);
        sig = Pan2.ar(sig, pan);
        sig = FreeVerb2.ar(sig[0], sig[1], reverb_mix, 0.88, 0.5);
        Out.ar(0, Limiter.ar(sig, 0.9));
    }).add;

    // ── BOMBARDAMENTO / MISSILE (194, 195) ──────────────────────
    // FM bassa + sub oscillator + BrownNoise filtrato.
    // Frequenza spinta nel registro grave, decay lungo.
    // reverb_mix alto per eventi distanti → rimbombo diffuso.
    SynthDef(\bomb, {
        |freq = 80, amp = 0.6, decay = 4.0, reverb_mix = 0.6, pan = 0.0|
        var env      = EnvGen.kr(Env.perc(0.008, decay,          1.0, -3), doneAction: 2);
        var env_fast = EnvGen.kr(Env.perc(0.001, decay * 0.35,   1.0, -5));

        var mod    = SinOsc.ar(freq * 2.1) * (freq * 2.0) * env_fast;
        var sig    = SinOsc.ar(freq + mod) * env;
        var sub    = SinOsc.ar(freq * 0.5) * env * 0.45;
        var rumble = RLPF.ar(BrownNoise.ar, freq * 1.5, 0.4) * env_fast * 0.35;

        sig = (sig + sub + rumble) * amp;
        sig = Pan2.ar(sig, pan);
        sig = FreeVerb2.ar(sig[0], sig[1], reverb_mix, 0.95, 0.25);
        Out.ar(0, Limiter.ar(sig, 0.9));
    }).add;

    s.sync;
    "[ SC ] SynthDef caricati: bell, combat, bomb".postln;

    // ── ROUTINE CAMPANE DI BACKGROUND ──────────────────────────
    // Scale pentatonica estesa — eterea, senza tensione armonica.
    // Scala scesa di un'ottava: registro grave-medio, più eterea
    ~bellScale = [
         55.00,  61.74,  73.42,  82.41,  92.50,
        110.00, 123.47, 146.83, 164.81, 184.99,
        220.00, 246.94, 293.66, 329.63
    ];

    ~bellRoutine = Routine({
        loop {
            Synth(\bell, [
                freq:  ~bellScale.choose,
                amp:   rrand(0.05, 0.14),
                decay: rrand(5.0, 11.0),
                pan:   rrand(-0.9, 0.9),
                room:  rrand(0.88, 0.97),
            ]);
            rrand(1.5, 5.0).wait;
        }
    }).play;

    "[ SC ] Background bell routine avviata".postln;

    // ── OSC RECEIVER: /event da Python fetcher (porta 9000) ────
    // msg: ['/event', freq, amp, reverb, decay_ms, event_code]
    // event_code: 190-196 (CAMEO)
    // Bombardamento: 194 (artiglieria/blindati), 195 (attacco aereo)
    // Scontro armato: tutto il resto

    thisProcess.openUDPPort(9000);

    OSCFunc.new({|msg|
        var freq       = msg[1].asFloat;
        var amp        = msg[2].asFloat;
        var reverb_mix = msg[3].asFloat;
        var decay_ms   = msg[4].asFloat;
        var event_code = msg[5].asInteger;
        var decay_s    = decay_ms / 1000.0;
        var pan        = rrand(-0.7, 0.7);

        if ((event_code == 194) || (event_code == 195), {
            // Bombardamento / missile → registro grave
            Synth(\bomb, [
                freq:       (freq * 0.25).max(45),
                amp:        (amp * 0.8).min(0.7),
                decay:      decay_s.clip(1.5, 8.0),
                reverb_mix: reverb_mix.max(0.35),
                pan:        pan,
            ]);
            ("[ bomb ] freq=" ++ (freq * 0.25).max(45).round(1)
             ++ " rev=" ++ reverb_mix.round(0.01)
             ++ " decay=" ++ decay_s.round(0.1) ++ "s").postln;
        }, {
            // Scontro armato → registro medio-alto
            Synth(\combat, [
                freq:       freq.clip(100, 500),
                amp:        (amp * 0.7).min(0.6),
                decay:      decay_s.clip(0.4, 4.0),
                reverb_mix: reverb_mix,
                pan:        pan,
            ]);
            ("[ combat ] freq=" ++ freq.round(1)
             ++ " rev=" ++ reverb_mix.round(0.01)
             ++ " decay=" ++ decay_s.round(0.1) ++ "s").postln;
        });
    }, '/event', nil);

    "[ SC ] In ascolto su porta 9000 — OSINT Cinetic pronto.".postln;

}, 20);
