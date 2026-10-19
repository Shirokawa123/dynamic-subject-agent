using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace DynamicSubject.MemorieCompanion;

// Use the same native TMP input machinery as the game's editable UI, including
// IME, selection and paste. The stripped IMGUI DoTextField cannot provide it.
internal sealed class NativeInput : IDisposable
{
    private readonly GameObject root;
    private readonly RectTransform shield;
    private readonly RectTransform fieldRect;
    private readonly TMP_InputField field;
    private readonly UnityEngine.Events.UnityAction<string> changedListener;
    private string lastReturned = "";
    private readonly Dictionary<string, RectTransform> buttons = new();
    private readonly Dictionary<string, UnityEngine.Events.UnityAction> buttonListeners = new();
    private readonly Dictionary<string, int> clicks = new();
    private readonly HashSet<string> visibleButtons = new();

    internal NativeInput(Action<string> changed)
    {
        TMP_FontAsset font = TMP_Settings.defaultFontAsset;
        foreach (var label in Resources.FindObjectsOfTypeAll<TextMeshProUGUI>())
        {
            if (label.gameObject.activeInHierarchy && label.font != null
                && label.text != null && label.text.Any(c => c >= '\u4e00' && c <= '\u9fff'))
            { font = label.font; break; }
        }
        root = new GameObject("MemorieCompanion.InputCanvas");
        UnityEngine.Object.DontDestroyOnLoad(root);
        var canvas = root.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = 32760;
        root.AddComponent<GraphicRaycaster>();
        shield = Child(root.transform, "ChatSurface");
        var shieldImage = shield.gameObject.AddComponent<Image>();
        shieldImage.color = new Color(.08f, .07f, .12f, .94f);
        shieldImage.raycastTarget = true;
        fieldRect = Child(root.transform, "MessageInput");
        var background = fieldRect.gameObject.AddComponent<Image>();
        background.color = new Color(.19f, .18f, .24f, 1);
        var viewport = Child(fieldRect, "Viewport");
        Stretch(viewport, 8);
        viewport.gameObject.AddComponent<RectMask2D>();
        var textRect = Child(viewport, "Text");
        Stretch(textRect, 0);
        var text = textRect.gameObject.AddComponent<TextMeshProUGUI>();
        text.font = font;
        text.color = Color.white;
        text.richText = false;
        text.raycastTarget = false;
        text.alignment = TextAlignmentOptions.TopLeft;
        field = fieldRect.gameObject.AddComponent<TMP_InputField>();
        field.textViewport = viewport;
        field.textComponent = text;
        field.fontAsset = font;
        field.targetGraphic = background;
        field.lineType = TMP_InputField.LineType.MultiLineNewline;
        field.richText = false;
        field.customCaretColor = true;
        field.caretColor = Color.white;
        changedListener = (UnityEngine.Events.UnityAction<string>)(value => changed(value));
        field.onValueChanged.AddListener(changedListener);
    }

    private static RectTransform Child(Transform parent, string name)
    {
        var gameObject = new GameObject(name);
        var rect = gameObject.AddComponent<RectTransform>();
        rect.SetParent(parent, false);
        rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0, 1);
        return rect;
    }

    private static void Stretch(RectTransform rect, float inset)
    {
        rect.anchorMin = Vector2.zero; rect.anchorMax = Vector2.one;
        rect.offsetMin = new Vector2(inset, inset); rect.offsetMax = new Vector2(-inset, -inset);
    }

    private static void Place(RectTransform target, Rect bounds, float scale)
    {
        target.anchoredPosition = new Vector2(bounds.x * scale, -bounds.y * scale);
        target.sizeDelta = new Vector2(bounds.width * scale, bounds.height * scale);
    }

    internal string Edit(Rect bounds, string text, int limit, float scale)
    {
        root.SetActive(true);
        Place(shield, new Rect(bounds.x - 16, bounds.y - 350, 400, 494), scale);
        Place(fieldRect, bounds, scale);
        field.textComponent.fontSize = 16 * scale;
        field.characterLimit = limit;
        if (text != lastReturned) Synchronize(text);
        lastReturned = field.text;
        return lastReturned;
    }

    internal void SetVisible(bool visible) => root.SetActive(visible);
    internal void BeginFrame()
    {
        visibleButtons.Clear();
        foreach (var key in clicks.Keys.ToArray())
            if (Time.frameCount - clicks[key] > 1) clicks.Remove(key);
    }
    internal bool CaptureButton(Rect bounds, string label, float scale)
    {
        if (!root.activeSelf) return false;
        visibleButtons.Add(label);
        if (!buttons.TryGetValue(label, out var rect))
        {
            rect = Child(root.transform, "Action." + label);
            var image = rect.gameObject.AddComponent<Image>();
            image.color = Color.clear;
            var button = rect.gameObject.AddComponent<Button>();
            button.targetGraphic = image;
            button.transition = Selectable.Transition.None;
            var listener = (UnityEngine.Events.UnityAction)(() => clicks[label] = Time.frameCount);
            buttonListeners[label] = listener;
            button.onClick.AddListener(listener);
            buttons[label] = rect;
        }
        rect.gameObject.SetActive(true);
        Place(rect, bounds, scale);
        return clicks.Remove(label);
    }
    internal void EndFrame()
    {
        foreach (var item in buttons)
            if (!visibleButtons.Contains(item.Key)) item.Value.gameObject.SetActive(false);
    }
    internal void Synchronize(string text)
    {
        if (field.text != text) field.SetTextWithoutNotify(text);
        lastReturned = text;
    }
    public void Dispose()
    {
        // Unity may destroy the native Canvas/children before this injected
        // MonoBehaviour's OnDestroy. A managed wrapper can then still exist.
        if (root == null) return;
        if (field != null) field.onValueChanged.RemoveListener(changedListener);
        foreach (var item in buttons)
        {
            if (item.Value == null) continue;
            var button = item.Value.GetComponent<Button>();
            if (button != null) button.onClick.RemoveListener(buttonListeners[item.Key]);
        }
        UnityEngine.Object.Destroy(root);
    }
}
