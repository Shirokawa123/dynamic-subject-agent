using DynamicSubject.MemorieCompanion;
using System.Text;

var root = new Uri(args[0]);
var path = args[1];
var mode = args.Length > 2 ? args[2] : "contract";
if (!new[] { "contract", "probe", "unicode-history", "reconnect-failure" }.Contains(mode))
    throw new ArgumentException("Unknown client contract mode; no connection or submission was attempted.");
using var firstClient = new CompanionClient(root);
var state = await firstClient.ConnectAsync();
if (!state.Ready) throw new Exception("Synthetic Interface must be ready.");
if (args.Length > 2 && args[2] == "probe")
{
    Console.WriteLine($"client-contract: read-only native connect ready; committed={state.Turns.Length}; no submission");
    return;
}
if (args.Length > 2 && args[2] == "unicode-history")
{
    if (state.Turns.Length != 1 || state.Turns[0].User.EnumerateRunes().Count() != 1000
        || state.Turns[0].Assistant.EnumerateRunes().Count() != 1200)
        throw new Exception("Valid scalar Unicode transcript was not preserved.");
    Console.WriteLine("client-contract: legal Unicode boundary history accepted");
    return;
}
if (args.Length > 2 && args[2] == "reconnect-failure")
{
    try { await firstClient.ConnectAsync(); throw new Exception("Broken reconnect accepted."); }
    catch (IOException) { }
    try
    {
        await firstClient.SubmitAsync(new PendingMessage("合成旧消息。", Guid.NewGuid().ToString("D"), state.Scope), false);
        throw new Exception("Failed reconnect retained an old session.");
    }
    catch (InvalidOperationException) { }
    Console.WriteLine("client-contract: failed reconnect cannot submit");
    return;
}
var original = new PendingMessage("合成跨语言消息：🌿", Guid.NewGuid().ToString("D"), state.Scope);
DraftFile.Save(path, new Draft(original.Text, original));
var initial = await firstClient.SubmitAsync(original, queryOnly: false);
if (!initial.Pending || initial.Settled) throw new Exception("Expected one pending operation.");
using var restartedClient = new CompanionClient(root);
await restartedClient.ConnectAsync();
var restored = DraftFile.Load(path);
var result = await restartedClient.SubmitAsync(restored.Pending, queryOnly: true);
if (!result.Ok || !result.Settled || result.State.Turns.Length != 1)
    throw new Exception("Read-only lookup must restore the completed turn.");
var settled = DraftFile.ApplyReply(restored, result);
if (settled.Text != "" || settled.Pending != null) throw new Exception("Original acknowledged draft not cleared.");
var edited = DraftFile.ApplyReply(new Draft("等待期间新写的草稿。", original), result);
if (edited.Text != "等待期间新写的草稿。" || edited.Pending != null)
    throw new Exception("Acknowledgment overwrote newer draft.");
var failed = DraftFile.ApplyReply(restored, new Reply(false, true, false, false, false, "", state));
if (failed.Text != original.Text || failed.Pending != null) throw new Exception("Failure lost draft.");
DraftFile.Save(path, edited);
if (DraftFile.Load(path).Text != edited.Text) throw new Exception("Unicode draft did not survive reopen.");
var maximumUnicode = string.Concat(Enumerable.Repeat("🌿", 1000));
var maximumDraft = new Draft(maximumUnicode, new PendingMessage(maximumUnicode, Guid.NewGuid().ToString("D"), state.Scope));
DraftFile.Save(path, maximumDraft);
var maximumRestored = DraftFile.Load(path);
if (maximumRestored.Text != maximumUnicode || maximumRestored.Pending.Text != maximumUnicode)
    throw new Exception("Maximum legal original and new draft did not survive JSON encoding.");
var notSent = new PendingMessage("合成未送达原消息。", Guid.NewGuid().ToString("D"), state.Scope);
var missing = await restartedClient.SubmitAsync(notSent, queryOnly: true);
if (!missing.CanResubmitOriginal || missing.Settled) throw new Exception("Missing original request must remain recoverable.");
var continued = await restartedClient.SubmitAsync(notSent, queryOnly: false);
if (!continued.Pending) throw new Exception("Explicit original submission did not start.");
var continuedResult = await restartedClient.SubmitAsync(notSent, queryOnly: true);
if (!continuedResult.Ok || !continuedResult.Settled) throw new Exception("Original submission was not recovered.");
try { using var invalid = new CompanionClient(new Uri("http://127.0.0.1:8798/redirect")); throw new Exception("Invalid root accepted."); }
catch (ArgumentException) { }
Console.WriteLine("client-contract: explicit sends/original lookup/not-found, unicode/reopen/new-draft/failure preserved");
