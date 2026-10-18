using System.Net;
using System.Text;
using System.Text.Json;

namespace DynamicSubject.MemorieCompanion;

internal sealed class Turn
{
    public string User { get; }
    public string Assistant { get; }
    public Turn(string user, string assistant) { User = user; Assistant = assistant; }
}
internal sealed class ChatState
{
    public bool Ready { get; }
    public string Scope { get; }
    public Turn[] Turns { get; }
    public string Message { get; }
    public ChatState(bool ready, string scope, Turn[] turns, string message)
    { Ready = ready; Scope = scope; Turns = turns; Message = message; }
}
internal sealed class PendingMessage
{
    public string Text { get; }
    public string RequestId { get; }
    public string Scope { get; }
    public PendingMessage(string text, string requestId, string scope)
    { Text = text; RequestId = requestId; Scope = scope; }
}
internal sealed class Draft
{
    public string Text { get; }
    public PendingMessage Pending { get; }
    public Draft(string text, PendingMessage pending) { Text = text; Pending = pending; }
}
internal sealed class Reply
{
    public bool Ok { get; }
    public bool Settled { get; }
    public bool Pending { get; }
    public bool CanAbandon { get; }
    public bool CanResubmitOriginal { get; }
    public string Message { get; }
    public ChatState State { get; }
    public Reply(bool ok, bool settled, bool pending, bool canAbandon, bool canResubmitOriginal, string message, ChatState state)
    { Ok = ok; Settled = settled; Pending = pending; CanAbandon = canAbandon;
      CanResubmitOriginal = canResubmitOriginal; Message = message; State = state; }
}

internal sealed class CompanionClient : IDisposable
{
    private readonly HttpClient http;
    private string token = "";

    internal CompanionClient(Uri root)
    {
        if (root.Scheme != "http" || root.Host != "127.0.0.1" || root.AbsolutePath != "/"
            || root.Query != "" || root.Fragment != "" || root.UserInfo != "")
            throw new ArgumentException("Exact loopback root required.");
        http = new HttpClient(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false })
        { BaseAddress = root, Timeout = TimeSpan.FromSeconds(75) };
    }

    private async Task<JsonDocument> ReadAsync(HttpRequestMessage request)
    {
        using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead).ConfigureAwait(false);
        if (response.StatusCode != HttpStatusCode.OK) throw new IOException("Local response unavailable.");
        using var stream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
        using var bounded = new MemoryStream();
        var buffer = new byte[4096];
        while (true)
        {
            var read = await stream.ReadAsync(buffer.AsMemory()).ConfigureAwait(false);
            if (read == 0) break;
            if (bounded.Length + read > 196608) throw new IOException("Local response too large.");
            bounded.Write(buffer, 0, read);
        }
        return JsonDocument.Parse(bounded.ToArray());
    }

    internal async Task<ChatState> ConnectAsync()
    {
        token = "";
        using var request = new HttpRequestMessage(HttpMethod.Get, "session");
        using var body = await ReadAsync(request).ConfigureAwait(false);
        if (body.RootElement.GetProperty("application").GetString() != "memorie-companion-s160"
            || body.RootElement.GetProperty("protocol").GetInt32() != 1)
            throw new IOException("Wrong companion application.");
        var candidateToken = body.RootElement.GetProperty("token").GetString() ?? "";
        if (candidateToken.Length < 32 || candidateToken.Length > 128) throw new IOException("Invalid local session.");
        using var status = await ReadAsync(new HttpRequestMessage(HttpMethod.Get, "status")).ConfigureAwait(false);
        var state = ParseState(status.RootElement);
        token = candidateToken;
        return state;
    }

    internal async Task<Reply> SubmitAsync(PendingMessage message, bool queryOnly)
    {
        if (token == "" || message.Text.EnumerateRunes().Count() is < 1 or > 1000
            || message.Text.Contains('\0') || !Guid.TryParseExact(message.RequestId, "D", out _))
            throw new InvalidOperationException("Verified original message required.");
        using var request = new HttpRequestMessage(HttpMethod.Post, queryOnly ? "result" : "send");
        request.Headers.Add("X-Chat-Token", token);
        request.Content = new StringContent(JsonSerializer.Serialize(new
            { text = message.Text, request_id = message.RequestId, scope_key = message.Scope }), Encoding.UTF8, "application/json");
        request.Content.Headers.ContentType!.CharSet = null;
        using var body = await ReadAsync(request).ConfigureAwait(false);
        var value = body.RootElement;
        var state = ParseState(value.GetProperty("state"));
        if (state.Scope != message.Scope) throw new IOException("Character scope changed.");
        if (!value.TryGetProperty("request_id", out var requestId) || requestId.GetString() != message.RequestId)
            throw new IOException("Original request mismatch.");
        var canResubmit = queryOnly && state.Ready
            && value.TryGetProperty("query_status", out var queryStatus) && queryStatus.GetString() == "not-found"
            && value.TryGetProperty("request_verified", out var verified) && verified.GetBoolean();
        return new Reply(value.GetProperty("ok").GetBoolean(),
            value.TryGetProperty("settled", out var settled) && settled.GetBoolean(),
            value.TryGetProperty("pending", out var pending) && pending.ValueKind == JsonValueKind.String,
            value.TryGetProperty("can_abandon", out var abandon) && abandon.GetBoolean(),
            canResubmit,
            value.TryGetProperty("message", out var info) ? info.GetString() ?? "" : "", state);
    }

    private static ChatState ParseState(JsonElement value)
    {
        if (value.GetProperty("subject_name").GetString() != "梅莫莉")
            throw new IOException("Unexpected character.");
        var ready = value.GetProperty("ready").GetBoolean();
        var scope = value.GetProperty("scope_key").GetString() ?? "";
        if (ready && (scope.Length != 64 || scope.Any(c => !Uri.IsHexDigit(c))))
            throw new IOException("Invalid character scope.");
        var turns = new List<Turn>();
        foreach (var item in value.GetProperty("turns").EnumerateArray())
        {
            if (turns.Count >= 20) throw new IOException("History too large.");
            var user = item.GetProperty("user_text").GetString() ?? "";
            var assistant = item.GetProperty("assistant_text").GetString() ?? "";
            if (user.EnumerateRunes().Count() > 1000 || assistant.EnumerateRunes().Count() > 1200)
                throw new IOException("Invalid transcript.");
            turns.Add(new Turn(user, assistant));
        }
        if (!ready && turns.Count != 0) throw new IOException("Unavailable history must be empty.");
        return new ChatState(ready, scope, turns.ToArray(), value.GetProperty("message").GetString() ?? "");
    }

    public void Dispose() => http.Dispose();
}

internal static class DraftFile
{
    internal static Draft ApplyReply(Draft current, Reply reply)
    {
        if (!reply.Settled) return current;
        var text = reply.Ok && current.Pending?.Text == current.Text ? "" : current.Text;
        return new Draft(text, null);
    }

    internal static Draft Load(string path)
    {
        if (!File.Exists(path)) return new Draft("", null);
        if (new FileInfo(path).Length > 32768) throw new IOException("Draft too large.");
        var value = JsonSerializer.Deserialize<Draft>(File.ReadAllText(path)) ?? throw new IOException("Invalid draft.");
        if (value.Text.Length > 2000 || value.Text.Contains('\0')) throw new IOException("Invalid draft.");
        if (value.Pending is { } pending && (pending.Text.EnumerateRunes().Count() is < 1 or > 1000
            || !Guid.TryParseExact(pending.RequestId, "D", out _) || pending.Scope.Length != 64))
            throw new IOException("Invalid original request.");
        return value;
    }

    internal static void Save(string path, Draft draft)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temporary = path + ".new";
        File.WriteAllText(temporary, JsonSerializer.Serialize(draft), Encoding.UTF8);
        File.Move(temporary, path, true);
    }
}
