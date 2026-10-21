using BepInEx;
using BepInEx.Unity.IL2CPP;
using Il2CppInterop.Runtime.Injection;
using UnityEngine;

namespace DynamicSubject.MemorieCompanion;

[BepInPlugin("local.dynamic-subject.memorie-companion", "Memorie Companion", "0.2.0")]
public sealed class Plugin : BasePlugin
{
    public override void Load()
    {
        CompanionPanel.Diagnostic = code => Log.LogWarning(code);
        ClassInjector.RegisterTypeInIl2Cpp<CompanionPanel>();
        AddComponent<CompanionPanel>();
        Log.LogInfo("Memorie Companion native HUD integration loaded; startup makes no model call.");
    }
}

public sealed class CompanionPanel : MonoBehaviour
{
    internal static Action<string> Diagnostic;
    private readonly CompanionClient client = new(new Uri("http://127.0.0.1:8798/"));
    private readonly string draftPath = Path.Combine(Paths.ConfigPath, "MemorieCompanion", "draft.json");
    private Draft draft = new("", null);
    private ChatState state = new(false, "", Array.Empty<Turn>(), "");
    private Task<ChatState> connecting;
    private Task<Reply> sending;
    private bool opened, initialized;
    private bool draftHealthy = true, draftLoaded = true;
    private string message = "";
    private NativeChatView view;
    private bool canAbandon, canResubmitOriginal;
    private float nextBind;
    private bool surfaceErrorLogged;

    public CompanionPanel(IntPtr pointer) : base(pointer) { }
    private bool Busy => connecting != null || sending != null;

    private void Update()
    {
        if (!initialized)
        {
            initialized = true;
            try { draft = DraftFile.Load(draftPath); }
            catch { draftHealthy = false; draftLoaded = false; message = "草稿读取失败，原文件保留。新输入可先复制保留。"; }
        }
        ConsumeReplies();
        try
        {
            if (view != null && !view.Game.Alive)
            {
                view.Dispose(); view = null; opened = false;
            }
            if (view == null && Time.unscaledTime >= nextBind)
            {
                nextBind = Time.unscaledTime + 2;
                var game = NativeGameUi.TryFind();
                if (game != null)
                {
                    view = new NativeChatView(game, SetOpen, text => Save(new Draft(text, draft.Pending)),
                        SendOrQuery, Connect, () => Save(draft), EndRequest);
                    surfaceErrorLogged = false;
                }
            }
            if (view == null) return;
            // Story, original dialogs and hidden HUD take priority. Reopening
            // after them is explicit, so the game cannot steal typing focus.
            if (opened && !view.Game.CanInteract) SetOpen(false);
            view.Refresh(state, draft, message, Busy, draftHealthy, draftLoaded, canAbandon, canResubmitOriginal);
        }
        catch (Exception error)
        {
            if (!surfaceErrorLogged)
            {
                surfaceErrorLogged = true;
                Diagnostic?.Invoke("companion-native-ui-unavailable:" + error.GetType().Name);
            }
            opened = false;
            view?.Dispose(); view = null;
            nextBind = Time.unscaledTime + 2;
            message = "对话暂时不可用，草稿保留。";
        }
    }

    private void LateUpdate()
    {
        if (view != null && view.Game.Alive) view.FinishLayout();
    }

    private void SetOpen(bool value)
    {
        if (value && (view == null || !view.Game.CanInteract)) return;
        opened = value;
        view?.SetOpen(value);
        if (value && !Busy) Connect();
    }

    private void Connect()
    {
        if (Busy) return;
        canAbandon = canResubmitOriginal = false;
        state = new ChatState(false, "", Array.Empty<Turn>(), "");
        message = "正在接通…";
        connecting = client.ConnectAsync();
    }

    private void ConsumeReplies()
    {
        if (connecting is { IsCompleted: true })
        {
            try { state = connecting.GetAwaiter().GetResult(); message = state.Message; }
            catch { message = "暂时无法接通，文字已保留。"; }
            connecting = null;
        }
        if (sending is not { IsCompleted: true }) return;
        try
        {
            var reply = sending.GetAwaiter().GetResult();
            state = reply.State; message = reply.Message;
            canAbandon = reply.CanAbandon;
            canResubmitOriginal = reply.CanResubmitOriginal;
            if (reply.Settled) Save(DraftFile.ApplyReply(draft, reply));
        }
        catch
        {
            canAbandon = canResubmitOriginal = false;
            message = "回复尚未确认。文字已保留，可以确认这轮结果。";
        }
        sending = null;
    }

    private void Save(Draft value)
    {
        draft = value;
        view?.Synchronize(value.Text);
        if (!draftLoaded) return;
        try { DraftFile.Save(draftPath, value); draftHealthy = true; }
        catch { draftHealthy = false; message = "草稿未能保存，文字仍在，请先复制保留。"; }
    }

    private void SendOrQuery()
    {
        if (!opened || view == null || !view.Game.CanInteract || Busy || !draftHealthy || !state.Ready) return;
        if (draft.Pending is { } pending)
        {
            if (state.Scope != pending.Scope) return;
            var queryOnly = !canResubmitOriginal;
            canAbandon = canResubmitOriginal = false;
            message = queryOnly ? "正在确认回复…" : "正在发送原来的那句话…";
            sending = client.SubmitAsync(pending, queryOnly);
            return;
        }
        if (string.IsNullOrWhiteSpace(draft.Text) || draft.Text.EnumerateRunes().Count() > 1000) return;
        var original = new PendingMessage(draft.Text, Guid.NewGuid().ToString("D"), state.Scope);
        Save(new Draft(draft.Text, original));
        if (draftHealthy)
        {
            message = "等待梅莫莉回复…";
            sending = client.SubmitAsync(original, queryOnly: false);
        }
    }

    private void EndRequest()
    {
        if (Busy || !canAbandon) return;
        Save(new Draft(draft.Text, null));
        canAbandon = canResubmitOriginal = false;
    }

    private void OnDestroy() { view?.Dispose(); client.Dispose(); }
}
