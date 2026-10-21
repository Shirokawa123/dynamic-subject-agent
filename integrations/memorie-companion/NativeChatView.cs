using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace DynamicSubject.MemorieCompanion;

// All controls share the original HUD's canvas, scale, raycasting and font.
// Only new objects/listeners are owned here; original widgets remain untouched.
internal sealed class NativeChatView : IDisposable
{
    internal readonly NativeGameUi Game;
    private readonly RectTransform root, entry, panel, historyPanel;
    private readonly CanvasGroup group;
    private readonly TMP_InputField input;
    private readonly TMP_Text replyText, statusText, historyText, sendText, countText;
    private readonly ScrollRect replyScroll, historyScroll;
    private readonly Button send, reconnect, retrySave, abandon;
    private readonly List<(Button Button, UnityEngine.Events.UnityAction Listener)> listeners = new();
    private readonly UnityEngine.Events.UnityAction<string> changedListener;
    private bool opened, history;
    private string lastReply = "", lastHistory = "";
    private bool scrollReply, scrollHistory;
    private bool statusShown = true;

    internal NativeChatView(NativeGameUi game, Action<bool> setOpen, Action<string> edit,
        Action sendOrQuery, Action connect, Action save, Action endRequest)
    {
        Game = game;
        try
        {
            entry = Child(game.Dock, "MemorieCompanion.ChatEntry");
            entry.gameObject.SetActive(false);
            entry.anchorMin = entry.anchorMax = Vector2.zero;
            entry.pivot = new Vector2(.5f, .5f);
            entry.anchoredPosition = new Vector2(594, 60);
            entry.sizeDelta = new Vector2(90, 90);
            var entryImage = game.Image(entry, "Button", true);
            var entryButton = entry.gameObject.AddComponent<Button>();
            entryButton.targetGraphic = entryImage;
            entryButton.transition = Selectable.Transition.ColorTint;
            var colors = entryButton.colors;
            colors.highlightedColor = new Color(1.16f, 1.12f, 1.06f, 1);
            colors.pressedColor = new Color(.78f, .72f, .7f, 1);
            colors.fadeDuration = .1f;
            entryButton.colors = colors;
            Listen(entryButton, () => { if (Game.CanInteract) setOpen(!opened); });
            var icon = Box(entry, "TalkIcon", 21, 10, 48, 42);
            game.Image(icon, "CompanionTalkIcon").color = NativeGameUi.Ink;
            Label(Box(entry, "Caption", 0, 51, 90, 26), "聊聊", 19, TextAlignmentOptions.Center);

            root = Child(game.Hud, "MemorieCompanion.Conversation");
            Stretch(root);
            group = root.gameObject.AddComponent<CanvasGroup>();
            group.alpha = 0;
            group.blocksRaycasts = group.interactable = false;
            panel = Child(root, "Conversation");
            panel.anchorMin = new Vector2(.1f, 0); panel.anchorMax = new Vector2(.9f, 0);
            panel.pivot = new Vector2(.5f, 0); panel.anchoredPosition = new Vector2(0, 120);
            panel.sizeDelta = new Vector2(0, 340);
            game.Image(panel, "TalkWindow", true, 2);
            Label(Box(panel, "Speaker", 44, 18, 230, 34), "梅莫莉", 26);
            var historyButton = ActionButton(panel, "聊天记录", () => ShowHistory(true));
            Right(historyButton.GetComponent<RectTransform>(), 112, 18, 150, 40);
            var close = ActionButton(panel, "收起", () => setOpen(false));
            Right(close.GetComponent<RectTransform>(), 24, 18, 80, 40);
            (replyScroll, replyText) = Scroller(panel, "Reply", 27);
            Inset(replyScroll.GetComponent<RectTransform>(), 44, 60, 44, 184);
            statusText = Label(Child(panel, "Status"), "", 19);
            Inset(statusText.rectTransform, 44, 162, 44, 130);
            statusText.color = NativeGameUi.Ink;
            var inputRect = Child(panel, "Message");
            Inset(inputRect, 44, 214, 210, 52);
            var background = game.Image(inputRect, "white-parts", true, 1);
            background.color = new Color(.035f, .12f, .216f, .58f);
            var viewport = Child(inputRect, "Viewport");
            Inset(viewport, 14, 10, 14, 10);
            viewport.gameObject.AddComponent<RectMask2D>();
            var text = Label(Child(viewport, "Text"), "", 23);
            Stretch(text.rectTransform);
            var placeholder = Label(Child(viewport, "Placeholder"), "想对梅莫莉说的话…", 23);
            Stretch(placeholder.rectTransform);
            placeholder.color = new Color(.68f, .73f, .83f, .8f);
            input = inputRect.gameObject.AddComponent<TMP_InputField>();
            input.textViewport = viewport;
            input.textComponent = (TextMeshProUGUI)text;
            input.placeholder = placeholder;
            input.fontAsset = game.Font;
            input.targetGraphic = background;
            input.lineType = TMP_InputField.LineType.MultiLineNewline;
            input.richText = false;
            input.characterLimit = 2000;
            input.customCaretColor = true;
            input.caretColor = NativeGameUi.Ink;
            input.selectionColor = new Color(.44f, .52f, .72f, .5f);
            changedListener = (UnityEngine.Events.UnityAction<string>)(value => edit(value));
            input.onValueChanged.AddListener(changedListener);
            send = ActionButton(panel, "发送", sendOrQuery);
            sendText = send.GetComponentInChildren<TextMeshProUGUI>();
            var sendRect = send.GetComponent<RectTransform>();
            sendRect.anchorMin = sendRect.anchorMax = new Vector2(1, 1);
            sendRect.pivot = new Vector2(1, 1);
            sendRect.anchoredPosition = new Vector2(-44, -214);
            sendRect.sizeDelta = new Vector2(150, 74);
            reconnect = ActionButton(panel, "重新接通", connect);
            Bottom(reconnect.GetComponent<RectTransform>(), 44, 10, 140, 34);
            retrySave = ActionButton(panel, "保存草稿", save);
            Bottom(retrySave.GetComponent<RectTransform>(), 194, 10, 140, 34);
            abandon = ActionButton(panel, "结束这轮", endRequest);
            Bottom(abandon.GetComponent<RectTransform>(), 344, 10, 140, 34);
            countText = Label(Child(panel, "Length"), "", 16, TextAlignmentOptions.Right);
            Right(countText.rectTransform, 48, 298, 210, 22);
            countText.color = new Color(.68f, .73f, .83f, 1);

            historyPanel = Child(root, "ChatHistory");
            historyPanel.anchorMin = new Vector2(0, .14f); historyPanel.anchorMax = new Vector2(0, .95f);
            historyPanel.pivot = new Vector2(0, 1); historyPanel.anchoredPosition = new Vector2(24, 0);
            historyPanel.sizeDelta = new Vector2(630, 0);
            game.Image(historyPanel, "WindowBase2", true, 2.5f);
            Label(Box(historyPanel, "Title", 44, 30, 330, 40), "聊天记录", 29);
            var back = ActionButton(historyPanel, "继续聊", () => ShowHistory(false));
            Right(back.GetComponent<RectTransform>(), 40, 32, 130, 42);
            (historyScroll, historyText) = Scroller(historyPanel, "CommittedConversation", 24);
            Inset(historyScroll.GetComponent<RectTransform>(), 48, 92, 48, 42);
            historyPanel.gameObject.SetActive(false);
            root.gameObject.SetActive(false);
        }
        catch
        {
            Dispose();
            throw;
        }
    }

    internal void SetOpen(bool value)
    {
        opened = value;
        history = false;
        if (value)
        {
            group.blocksRaycasts = group.interactable = true;
            root.gameObject.SetActive(true);
            panel.gameObject.SetActive(true);
            historyPanel.gameObject.SetActive(false);
            // Focus only follows an explicit click, never an async reply/rebind.
            input.ActivateInputField();
        }
        else
        {
            ReleaseInput();
            group.blocksRaycasts = group.interactable = false;
        }
    }

    private void ShowHistory(bool value)
    {
        if (!opened || !Game.CanInteract) return;
        history = value;
        ReleaseInput();
        panel.gameObject.SetActive(!value);
        historyPanel.gameObject.SetActive(value);
        if (!value) input.ActivateInputField();
        scrollHistory = true;
    }

    internal void Synchronize(string text)
    {
        if (input != null && input.text != text) input.SetTextWithoutNotify(text);
    }

    internal void Refresh(ChatState state, Draft draft, string message, bool busy,
        bool draftHealthy, bool draftLoaded, bool canAbandon, bool canResubmit)
    {
        entry.gameObject.SetActive(Game.CanInteract && !opened);
        group.alpha = Mathf.MoveTowards(group.alpha, opened ? 1 : 0, Time.unscaledDeltaTime / .12f);
        if (!opened && group.alpha <= 0) root.gameObject.SetActive(false);
        if (!opened) return;
        Synchronize(draft.Text);
        var content = state.Turns.Length == 0 ? "从这里开始，和梅莫莉说说今天的事。" : state.Turns[^1].Assistant;
        if (lastReply != content)
        {
            replyText.text = lastReply = content;
            scrollReply = true;
        }
        var transcript = string.Join("\n\n", state.Turns.Select(t => "你\n" + t.User + "\n\n梅莫莉\n" + t.Assistant));
        if (draft.Pending is { } pendingOriginal)
            transcript += "\n\n等待确认的原话（尚未加入聊天记录）\n" + pendingOriginal.Text;
        if (lastHistory != transcript)
        {
            historyText.text = lastHistory = transcript;
            scrollHistory = true;
        }
        var length = draft.Text.EnumerateRunes().Count();
        var status = message;
        if (length > 1000) status = "这段话超过1000字，草稿已保留，请分段后再发送。";
        if (draft.Pending is { } pending)
        {
            var original = new System.Globalization.StringInfo(pending.Text);
            var excerpt = original.LengthInTextElements > 24 ? original.SubstringByTextElements(0, 24) + "…" : pending.Text;
            status = "原话：" + excerpt + "\n" + (status == "" ? "聊天记录可核对原话，新草稿已保留。" : status);
        }
        statusText.text = status;
        var showStatus = status != "";
        if (statusShown != showStatus)
        {
            statusShown = showStatus;
            panel.sizeDelta = new Vector2(0, showStatus ? 340 : 294);
            statusText.gameObject.SetActive(showStatus);
            var composer = input.GetComponent<RectTransform>();
            composer.offsetMax = new Vector2(composer.offsetMax.x, showStatus ? -214 : -168);
            send.GetComponent<RectTransform>().anchoredPosition = new Vector2(-44, showStatus ? -214 : -168);
            countText.rectTransform.anchoredPosition = new Vector2(-48, showStatus ? -298 : -252);
        }
        countText.text = length > 800 ? length + " / 1000" : "";
        sendText.text = draft.Pending == null ? (busy ? "等待回复…" : "发送") : canResubmit ? "继续发原话" : "确认回复";
        var ready = !busy && draftHealthy && state.Ready && (draft.Pending is { } originalMessage
            ? originalMessage.Scope == state.Scope : length is > 0 and <= 1000 && !string.IsNullOrWhiteSpace(draft.Text));
        send.interactable = ready;
        sendText.color = ready ? NativeGameUi.Ink : new Color(.62f, .58f, .55f, .6f);
        reconnect.gameObject.SetActive(!busy && !state.Ready);
        retrySave.gameObject.SetActive(!busy && !draftHealthy && draftLoaded);
        abandon.gameObject.SetActive(!busy && draft.Pending != null && canAbandon);
    }

    internal void FinishLayout()
    {
        if (!opened) return;
        if (scrollReply) { replyScroll.verticalNormalizedPosition = 1; scrollReply = false; }
        if (history && scrollHistory) { historyScroll.verticalNormalizedPosition = 0; scrollHistory = false; }
    }

    private void ReleaseInput()
    {
        if (input != null) input.DeactivateInputField();
        var events = EventSystem.current;
        var selected = events != null ? events.currentSelectedGameObject : null;
        if (selected != null && ((root != null && selected.transform.IsChildOf(root))
            || (entry != null && selected.transform.IsChildOf(entry))))
            events.SetSelectedGameObject(null);
    }

    private Button ActionButton(Transform parent, string caption, Action action)
    {
        var rect = Child(parent, "Action." + caption);
        var image = Game.Image(rect, "AnswerBase", true, 3);
        var button = rect.gameObject.AddComponent<Button>();
        Game.StyleButton(button, image);
        var label = Label(Child(rect, "Caption"), caption, 21, TextAlignmentOptions.Center);
        Stretch(label.rectTransform);
        Listen(button, () => { if (Game.CanInteract && opened) action(); });
        return button;
    }

    private void Listen(Button button, Action action)
    {
        var listener = (UnityEngine.Events.UnityAction)(() => action());
        listeners.Add((button, listener));
        button.onClick.AddListener(listener);
    }

    private (ScrollRect Scroll, TMP_Text Text) Scroller(Transform parent, string name, int size)
    {
        var rect = Child(parent, name);
        var viewport = Child(rect, "Viewport");
        Inset(viewport, 0, 0, 16, 0);
        var hit = viewport.gameObject.AddComponent<Image>();
        hit.color = Color.clear;
        viewport.gameObject.AddComponent<RectMask2D>();
        var label = Label(Child(viewport, "Content"), "", size);
        label.rectTransform.anchorMin = new Vector2(0, 1); label.rectTransform.anchorMax = Vector2.one;
        label.rectTransform.pivot = new Vector2(0, 1);
        label.rectTransform.sizeDelta = Vector2.zero;
        label.rectTransform.anchoredPosition = Vector2.zero;
        label.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
        var scroll = rect.gameObject.AddComponent<ScrollRect>();
        scroll.viewport = viewport; scroll.content = label.rectTransform;
        scroll.horizontal = false; scroll.vertical = true;
        scroll.movementType = ScrollRect.MovementType.Clamped;
        scroll.scrollSensitivity = 32;
        var track = Child(rect, "Scrollbar");
        track.anchorMin = new Vector2(1, 0); track.anchorMax = Vector2.one;
        track.offsetMin = new Vector2(-7, 0); track.offsetMax = Vector2.zero;
        var thumb = Child(track, "Handle"); Stretch(thumb);
        var image = Game.Image(thumb, "white-parts", true);
        image.color = NativeGameUi.Muted;
        var bar = track.gameObject.AddComponent<Scrollbar>();
        bar.handleRect = thumb; bar.targetGraphic = image;
        bar.direction = Scrollbar.Direction.BottomToTop;
        scroll.verticalScrollbar = bar;
        scroll.verticalScrollbarVisibility = ScrollRect.ScrollbarVisibility.AutoHide;
        return (scroll, label);
    }

    private TMP_Text Label(RectTransform rect, string text, int size, TextAlignmentOptions alignment = TextAlignmentOptions.TopLeft)
    {
        var label = rect.gameObject.AddComponent<TextMeshProUGUI>();
        label.font = Game.Font; label.text = text; label.fontSize = size;
        label.color = NativeGameUi.Ink; label.richText = false; label.raycastTarget = false;
        label.alignment = alignment; label.overflowMode = TextOverflowModes.Overflow;
        return label;
    }

    private static RectTransform Child(Transform parent, string name)
    {
        var rect = new GameObject(name).AddComponent<RectTransform>();
        rect.SetParent(parent, false);
        rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0, 1);
        return rect;
    }
    private static void Stretch(RectTransform rect) => Inset(rect, 0, 0, 0, 0);
    private static void Inset(RectTransform rect, float left, float top, float right, float bottom)
    {
        rect.anchorMin = Vector2.zero; rect.anchorMax = Vector2.one;
        rect.offsetMin = new Vector2(left, bottom); rect.offsetMax = new Vector2(-right, -top);
    }
    private static RectTransform Box(Transform parent, string name, float x, float y, float width, float height)
    {
        var rect = Child(parent, name);
        rect.anchoredPosition = new Vector2(x, -y); rect.sizeDelta = new Vector2(width, height);
        return rect;
    }
    private static void Right(RectTransform rect, float right, float top, float width, float height)
    {
        rect.anchorMin = rect.anchorMax = new Vector2(1, 1); rect.pivot = new Vector2(1, 1);
        rect.anchoredPosition = new Vector2(-right, -top); rect.sizeDelta = new Vector2(width, height);
    }
    private static void Bottom(RectTransform rect, float left, float bottom, float width, float height)
    {
        rect.anchorMin = rect.anchorMax = Vector2.zero; rect.pivot = Vector2.zero;
        rect.anchoredPosition = new Vector2(left, bottom); rect.sizeDelta = new Vector2(width, height);
    }

    public void Dispose()
    {
        if (root != null) ReleaseInput();
        if (input != null) input.onValueChanged.RemoveListener(changedListener);
        foreach (var item in listeners)
            if (item.Button != null) item.Button.onClick.RemoveListener(item.Listener);
        if (entry != null) UnityEngine.Object.Destroy(entry.gameObject);
        if (root != null) UnityEngine.Object.Destroy(root.gameObject);
    }
}
