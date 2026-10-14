using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using TAOSW.DSC_Decoder.Core;
using TAOSW.DSC_Decoder.Core.TAOSW.DSC_Decoder.Core;

var protocol = new StreamWriter(Console.OpenStandardOutput()) { AutoFlush = true };
Console.SetOut(TextWriter.Null);
const int MaxStreamStates = 64;
var states = new Dictionary<string, DecoderState>();

string? line;
while ((line = Console.In.ReadLine()) is not null)
{
    var messages = new List<object>();
    var resets = 0;
    var evictions = 0;
    try
    {
        using var doc = JsonDocument.Parse(line);
        var root = doc.RootElement;
        var encoding = root.GetProperty("encoding").GetString() ?? "";
        var frequency = root.GetProperty("frequency_hz").GetInt32();
        if (encoding == "pcm_s16le" && IsDscFrequency(frequency))
        {
            var rate = root.GetProperty("sample_rate_hz").GetInt32();
            var lineage = root.TryGetProperty("physical_lineage", out var lineageElement)
                ? lineageElement.GetString()
                : null;
            var receiver = root.TryGetProperty("receiver_id", out var receiverElement)
                ? receiverElement.GetString()
                : null;
            var streamKey = $"{lineage ?? receiver ?? "unknown"}|{frequency}|{rate}";
            var pcm = Convert.FromBase64String(root.GetProperty("payload_b64").GetString() ?? "");
            if (pcm.Length > 0 && pcm.Length % 2 == 0 && pcm.Length <= 262144)
            {
                var session = root.TryGetProperty("session_id", out var sessionElement) && sessionElement.ValueKind == JsonValueKind.String
                    ? sessionElement.GetString() : null;
                uint? sequence = root.TryGetProperty("sequence", out var sequenceElement) && sequenceElement.ValueKind == JsonValueKind.Number
                    && sequenceElement.TryGetUInt32(out var seq) ? seq : null;
                var observedAt = root.TryGetProperty("observed_at", out var observedElement) && observedElement.ValueKind == JsonValueKind.String
                    && DateTimeOffset.TryParse(observedElement.GetString(), out var observed) ? observed : DateTimeOffset.MinValue;
                if (!states.TryGetValue(streamKey, out var state) ||
                    state.NeedsReset(session, sequence, observedAt))
                {
                    if (state is not null) resets++;
                    if (!states.ContainsKey(streamKey) && states.Count >= MaxStreamStates)
                    {
                        var oldest = states.MinBy(item => item.Value.LastUsedUtc).Key;
                        states.Remove(oldest);
                        evictions++;
                    }
                    states[streamKey] = state = new DecoderState(rate);
                }
                state.Process(pcm);
                state.MarkFrame(session, sequence, observedAt, pcm.Length / 2);
                var emitted = new HashSet<string>();
                foreach (var msg in state.Drain())
                {
                    if (msg.Status != "OK") continue;
                    var key = string.Join(",", msg.Symbols ?? new List<int>());
                    if (emitted.Add(key)) messages.Add(ToWire(msg));
                }
            }
        }
    }
    catch { }
    protocol.WriteLine(JsonSerializer.Serialize(new { messages, continuity_resets = resets, state_evictions = evictions }));
}

static bool IsDscFrequency(int hz)
{
    // This bridge implements MF/HF DSC only: 100 Bd, 170 Hz shift.
    // VHF channel 70 uses 1200 Bd and 1300/2100 Hz tones and requires a
    // separate decoder contract rather than pretending this path supports it.
    int[] allowed = { 2_187_500, 4_207_500, 6_312_000, 8_414_500, 12_577_000, 16_804_500 };
    return allowed.Any(value => Math.Abs(value - hz) <= 100);
}

static object ToWire(DSCMessage msg)
{
    var payload = new Dictionary<string, object?>
    {
        ["category"] = msg.Category.ToString().ToLowerInvariant(),
        ["mmsi"] = Regex.Match(msg.From ?? "", @"\d{6,9}").Value is var m && m.Length > 0 ? m : null,
        ["nature_code"] = msg.Nature?.ToString().ToLowerInvariant(),
        ["format"] = msg.Format.ToString(),
        ["status"] = msg.Status,
    };
    var pos = ParsePosition(msg.Position);
    if (pos is not null)
    {
        payload["latitude"] = pos.Value.lat;
        payload["longitude"] = pos.Value.lon;
    }
    var material = string.Join(",", msg.Symbols ?? new List<int>());
    var digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(material))).Substring(0, 24).ToLowerInvariant();
    return new { kind = "dsc", payload, message_id = $"taosw_{digest}" };
}

static (double lat, double lon)? ParsePosition(string? value)
{
    if (string.IsNullOrWhiteSpace(value)) return null;
    var match = Regex.Match(value, @"^(\d{2}) (\d{2})([NS]) (\d{3}) (\d{2})([EW])$");
    if (!match.Success) return null;
    double lat = int.Parse(match.Groups[1].Value) + int.Parse(match.Groups[2].Value) / 60.0;
    double lon = int.Parse(match.Groups[4].Value) + int.Parse(match.Groups[5].Value) / 60.0;
    if (match.Groups[3].Value == "S") lat = -lat;
    if (match.Groups[6].Value == "W") lon = -lon;
    return (lat, lon);
}

sealed class DecoderState
{
    const float MarkHz = 1615;
    const float SpaceHz = 1785;
    readonly DSCDecoder decoder;
    readonly GMDSSDecoder[] gmdss;
    readonly int samplesPerSymbol;
    readonly List<float> pendingSamples = new();
    readonly ConcurrentQueue<DSCMessage> pending = new();
    readonly int sampleRate;
    string? lastSession;
    uint? lastSequence;
    DateTimeOffset lastObservedAt = DateTimeOffset.MinValue;
    double lastFrameDurationS;
    public DateTimeOffset LastUsedUtc { get; private set; } = DateTimeOffset.UtcNow;

    public bool NeedsReset(string? session, uint? sequence, DateTimeOffset observedAt)
    {
        if (DateTimeOffset.UtcNow - LastUsedUtc > TimeSpan.FromMinutes(10)) return true;
        if (lastSession != null && session != null && lastSession != session) return true;
        if (lastSequence.HasValue && sequence.HasValue &&
            sequence.Value != unchecked(lastSequence.Value + 1)) return true;
        if (lastObservedAt != DateTimeOffset.MinValue && observedAt != DateTimeOffset.MinValue)
        {
            var seconds = (observedAt - lastObservedAt).TotalSeconds;
            if (seconds < -0.2 || seconds > Math.Max(0.25, lastFrameDurationS * 4 + 0.05)) return true;
        }
        return false;
    }

    public void MarkFrame(string? session, uint? sequence, DateTimeOffset observedAt, int samples)
    {
        lastSession = session;
        lastSequence = sequence;
        lastObservedAt = observedAt;
        lastFrameDurationS = (double)samples / sampleRate;
        LastUsedUtc = DateTimeOffset.UtcNow;
    }

    public DecoderState(int sampleRate)
    {
        // MF/HF DSC receivers stay on the assigned RF channel. J2B
        // demodulation yields the standard 1615/1785 Hz audio pair directly.
        // The tones are fixed, so bypass the FFT auto-tuner entirely.
        if (sampleRate < 100 || sampleRate % 100 != 0)
            throw new ArgumentException("DSC sample rate must be divisible by 100", nameof(sampleRate));
        this.sampleRate = sampleRate;
        samplesPerSymbol = sampleRate / 100;
        decoder = new DSCDecoder(100, sampleRate);
        gmdss = Enumerable.Range(0, DSCDecoder.SlideWindowsNumber).Select(_ => new GMDSSDecoder()).ToArray();
        foreach (var item in gmdss) item.OnMessageDecoded += msg => pending.Enqueue(msg);
    }

    public void Process(byte[] pcm)
    {
        var signal = new float[pcm.Length / 2];
        for (var i = 0; i < signal.Length; i++)
        {
            short sample = (short)(pcm[i * 2] | (pcm[i * 2 + 1] << 8));
            signal[i] = sample / 32768f;
        }
        // DSC is 100 baud. Incoming WebSDR audio packets are not guaranteed
        // to contain a whole number of 10 ms symbols. The upstream decoder
        // rounds partial trailing windows up, inventing bits and breaking phase.
        // Keep at most one partial symbol between packets in this stream.
        pendingSamples.AddRange(signal);
        var alignedCount = pendingSamples.Count / samplesPerSymbol * samplesPerSymbol;
        if (alignedCount == 0) return;
        var aligned = pendingSamples.GetRange(0, alignedCount).ToArray();
        pendingSamples.RemoveRange(0, alignedCount);
        var bits = decoder.DecodeFSK(aligned, MarkHz, SpaceHz);
        for (var i = 0; i < Math.Min(bits.Length, gmdss.Length); i++) gmdss[i].AddBits(bits[i]);
    }

    public IEnumerable<DSCMessage> Drain()
    {
        while (pending.TryDequeue(out var msg)) yield return msg;
    }
}
