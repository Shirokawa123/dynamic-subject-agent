using BepInEx;
using BepInEx.Unity.IL2CPP;
using Il2CppInterop.Runtime.Injection;
using UnityEngine;
using System.Reflection;
using System.Text;

namespace DynamicSubject.MemorieCompanion;

[BepInPlugin("local.dynamic-subject.memorie-companion", "Memorie Companion", "0.1.0")]
public sealed class Plugin : BasePlugin
{
    public override void Load()
    {
        CompanionPanel.Diagnostic = code => Log.LogWarning(code);
        ClassInjector.RegisterTypeInIl2Cpp<CompanionPanel>();
        AddComponent<CompanionPanel>();
        Log.LogInfo("Memorie Companion panel loaded; no model is called by startup.");
    }
}

public sealed class CompanionPanel : MonoBehaviour
{
    internal static Action<string> Diagnostic;
    private readonly CompanionClient client = new(new Uri("http://127.0.0.1:8798/"));
    private readonly string draftPath = Path.Combine(Paths.ConfigPath, "MemorieCompanion", "draft.json");
    private Draft draft = new("", null);
    private ChatState state = new(false, "", Array.Empty<Turn>(), "点击连接，继续和梅莫莉聊聊。");
    private Task<ChatState> connecting;
    private Task<Reply> sending;
    private bool opened;
    private bool initialized;
    private bool draftHealthy = true;
    private bool draftLoaded = true;
    private string message = "";
    private NativeGui gui;
    private bool canAbandon;
    private bool canResubmitOriginal;
    private Vector2 historyScroll = new(0, float.MaxValue);
    private bool surfaceErrorLogged;

    public CompanionPanel(IntPtr pointer) : base(pointer) { }

    private void Update()
    {
        if (!initialized)
        {
            initialized = true;
            try { draft = DraftFile.Load(draftPath); }
            catch { draftHealthy = false; draftLoaded = false; message = "草稿读取失败，原文件保留。新输入可先复制保留。"; }
        }
        if (connecting is { IsCompleted: true })
        {
            try { state = connecting.GetAwaiter().GetResult(); message = state.Message; historyScroll.y = float.MaxValue; }
            catch { message = "暂时无法连接，输入的文字会保留。"; }
            connecting = null;
        }
        if (sending is { IsCompleted: true })
        {
            try
            {
                var reply = sending.GetAwaiter().GetResult();
                state = reply.State; message = reply.Message;
                canAbandon = reply.CanAbandon;
                canResubmitOriginal = reply.CanResubmitOriginal;
                historyScroll.y = float.MaxValue;
                if (reply.Settled)
                {
                    Save(DraftFile.ApplyReply(draft, reply));
                }
            }
            catch { canAbandon = canResubmitOriginal = false; message = "这轮结果尚未确认。请查询原请求，文字已保留。"; }
            sending = null;
        }
    }

    private void Save(Draft value)
    {
        if (draft.Pending?.RequestId != value.Pending?.RequestId) historyScroll.y = float.MaxValue;
        draft = value;
        if (!draftLoaded) return;
        try { DraftFile.Save(draftPath, value); draftHealthy = true; }
        catch { draftHealthy = false; message = "草稿未能写入磁盘，文字仍留在面板，请先复制保留。"; }
    }

    private void OnGUI()
    {
        if (!initialized) return;
        try
        {
            gui ??= new NativeGui();
            using var fontScope = gui.UseChineseFont();
            var x = Math.Max(8, Screen.width - 416);
            var y = Math.Max(8, Screen.height - 510);
            if (!opened)
            {
                if (gui.Button(new Rect(x + 280, Screen.height - 48, 120, 34), "和梅莫莉聊聊")) opened = true;
                return;
            }
            gui.Box(new Rect(x, y, 400, 494), "");
            gui.Label(new Rect(x + 16, y + 12, 285, 28), "梅莫莉");
            if (gui.Button(new Rect(x + 334, y + 12, 50, 28), "收起")) opened = false;
            var transcript = string.Join("\n\n", state.Turns.Select(t => "你：" + t.User + "\n梅莫莉：" + t.Assistant));
            if (draft.Pending is { } displayedOriginal)
                transcript += "\n\n待确认的原消息：\n" + displayedOriginal.Text;
            historyScroll = gui.ScrollText(new Rect(x + 16, y + 52, 368, 228), transcript, historyScroll);
            var statusText = message != "" ? message : state.Message;
            if (draft.Text.EnumerateRunes().Count() > 1000)
                statusText = "这段话超过1000字，草稿已保留，请分段后再发送。";
            if (draft.Pending is { } waiting)
            {
                var originalText = new System.Globalization.StringInfo(waiting.Text);
                var excerpt = originalText.LengthInTextElements > 18
                    ? originalText.SubstringByTextElements(0, 18) + "…" : waiting.Text;
                statusText = "原消息：" + excerpt + "\n" + statusText;
            }
            gui.WrappedLabel(new Rect(x + 16, y + 284, 368, 60), statusText);
            var text = gui.TextArea(new Rect(x + 16, y + 350, 368, 78), draft.Text, 2000);
            if (text != draft.Text) Save(new Draft(text, draft.Pending));
            var busy = connecting != null || sending != null;
            if (!busy && gui.Button(new Rect(x + 16, y + 442, 92, 34), "连接"))
            {
                canAbandon = canResubmitOriginal = false;
                state = new ChatState(false, "", Array.Empty<Turn>(), "正在连接，文字已保留。");
                connecting = client.ConnectAsync();
            }
            if (!busy && !draftHealthy && draftLoaded
                && gui.Button(new Rect(x + 116, y + 442, 108, 34), "重试保存")) Save(draft);
            if (draft.Pending is { } pending)
            {
                if (!busy && canAbandon && gui.Button(new Rect(x + 116, y + 442, 108, 34), "结束这轮"))
                {
                    Save(new Draft(draft.Text, null));
                    canAbandon = canResubmitOriginal = false;
                    return;
                }
                if (!busy && draftHealthy && state.Ready && state.Scope == pending.Scope
                    && gui.Button(new Rect(x + 232, y + 442, 152, 34),
                        canResubmitOriginal ? "继续提交原消息" : "查询这轮结果"))
                {
                    var queryOnly = !canResubmitOriginal;
                    canAbandon = canResubmitOriginal = false;
                    sending = client.SubmitAsync(pending, queryOnly);
                }
            }
            else if (!busy && draftHealthy && state.Ready && !string.IsNullOrWhiteSpace(draft.Text)
                && draft.Text.EnumerateRunes().Count() <= 1000
                && gui.Button(new Rect(x + 280, y + 442, 104, 34), "发送"))
            {
                var original = new PendingMessage(draft.Text, Guid.NewGuid().ToString("D"), state.Scope);
                Save(new Draft(draft.Text, original));
                if (draftHealthy) sending = client.SubmitAsync(original, queryOnly: false);
            }
        }
        catch (Exception error)
        {
            if (!surfaceErrorLogged)
            {
                surfaceErrorLogged = true;
                var cause = error;
                while (cause.InnerException != null) cause = cause.InnerException;
                Diagnostic?.Invoke("companion-panel-unavailable:" + NativeGui.Stage + ":" + cause.GetType().Name);
            }
            message = "对话面板暂时不可用，草稿保留。";
        }
    }

    private void OnDestroy() => client.Dispose();
}

// Only the generated CoreModule is a compile reference. Resolve the game's own
// IMGUI module at runtime; missing stripped APIs leave the panel unavailable.
internal sealed class NativeGui
{
    internal static string Stage = "initialize";
    private readonly Type type;
    private readonly object chineseFont;
    internal NativeGui()
    {
        type = Type.GetType("UnityEngine.GUI, UnityEngine.IMGUIModule", throwOnError: true)!;
        var font = Type.GetType("UnityEngine.Font, UnityEngine.TextRenderingModule", throwOnError: true)!;
        chineseFont = font.GetMethod("CreateDynamicFontFromOSFont", new[] { typeof(string), typeof(int) })!
            .Invoke(null, new object[] { "Microsoft YaHei", 16 });
    }
    internal IDisposable UseChineseFont()
    {
        var skin = type.GetProperty("skin", BindingFlags.Public | BindingFlags.Static)!.GetValue(null)!;
        var font = skin.GetType().GetProperty("font")!;
        var previous = font.GetValue(skin);
        font.SetValue(skin, chineseFont);
        return new FontScope(() => font.SetValue(skin, previous));
    }
    private sealed class FontScope : IDisposable
    {
        private readonly Action restore;
        internal FontScope(Action restore) => this.restore = restore;
        public void Dispose() => restore();
    }
    private object Call(string name, Type[] types, params object[] args)
    {
        Stage = name;
        return (type.GetMethod(name, BindingFlags.Public | BindingFlags.Static, null, types, null)
            ?? throw new MissingMethodException(name)).Invoke(null, args);
    }
    internal bool Button(Rect rect, string text) => (bool)Call("Button", new[] { typeof(Rect), typeof(string) }, rect, text)!;
    internal void Label(Rect rect, string text) => Call("Label", new[] { typeof(Rect), typeof(string) }, rect, text);
    internal void WrappedLabel(Rect rect, string text)
    {
        var styleType = Type.GetType("UnityEngine.GUIStyle, UnityEngine.IMGUIModule", true)!;
        var skin = type.GetProperty("skin", BindingFlags.Public | BindingFlags.Static)!.GetValue(null)!;
        var style = skin.GetType().GetProperty("label")!.GetValue(skin)!;
        var wrap = styleType.GetProperty("wordWrap")!;
        var previous = wrap.GetValue(style);
        try { wrap.SetValue(style, true); Call("Label", new[] { typeof(Rect), typeof(string), styleType }, rect, text, style); }
        finally { wrap.SetValue(style, previous); }
    }
    internal void Box(Rect rect, string text) => Call("Box", new[] { typeof(Rect), typeof(string) }, rect, text);
    internal string TextArea(Rect rect, string text, int limit) =>
        (string)Call("TextArea", new[] { typeof(Rect), typeof(string), typeof(int) }, rect, text, limit)!;
    internal Vector2 ScrollText(Rect rect, string text, Vector2 scroll)
    {
        var contentType = Type.GetType("UnityEngine.GUIContent, UnityEngine.IMGUIModule", true)!;
        var styleType = Type.GetType("UnityEngine.GUIStyle, UnityEngine.IMGUIModule", true)!;
        var skin = type.GetProperty("skin", BindingFlags.Public | BindingFlags.Static)!.GetValue(null)!;
        var style = skin.GetType().GetProperty("label")!.GetValue(skin)!;
        var wrap = styleType.GetProperty("wordWrap")!;
        var oldWrap = wrap.GetValue(style);
        var richText = styleType.GetProperty("richText")!;
        var oldRichText = richText.GetValue(style);
        var content = Activator.CreateInstance(contentType, new object[] { text })!;
        wrap.SetValue(style, true);
        richText.SetValue(style, false);
        try
        {
            var width = rect.width - 22;
            Stage = "CalcHeight";
            var height = Math.Max(rect.height, (float)styleType.GetMethod("CalcHeight", new[] { contentType, typeof(float) })!
                .Invoke(style, new object[] { content, width })!);
            var result = (Vector2)Call("BeginScrollView", new[] { typeof(Rect), typeof(Vector2), typeof(Rect) },
                rect, scroll, new Rect(0, 0, width, height))!;
            try { Call("Label", new[] { typeof(Rect), contentType, styleType }, new Rect(0, 0, width, height), content, style); }
            finally { Call("EndScrollView", Type.EmptyTypes); }
            return result;
        }
        finally { wrap.SetValue(style, oldWrap); richText.SetValue(style, oldRichText); }
    }
}
