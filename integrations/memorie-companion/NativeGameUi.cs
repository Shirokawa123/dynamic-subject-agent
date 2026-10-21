using TMPro;
using UnityEngine;
using UnityEngine.UI;
using Yarn.Unity;

namespace DynamicSubject.MemorieCompanion;

// Observe the original UI; never invoke its buttons, presenters or story runner.
internal sealed class NativeGameUi
{
    internal readonly RectTransform Dock;
    internal readonly Transform Hud;
    internal readonly TMP_FontAsset Font;
    private readonly DialogueRunner[] runners;
    private readonly CanvasGroup[] modalGroups;
    private readonly Dictionary<string, Sprite> sprites;
    internal static readonly Color Ink = new(1f, .937f, .835f, 1);
    internal static readonly Color Muted = new(.706f, .545f, .533f, 1);

    private NativeGameUi(RectTransform dock, TMP_FontAsset font, Dictionary<string, Sprite> sprites)
    {
        Dock = dock;
        Hud = dock.parent;
        Font = font;
        this.sprites = sprites;
        runners = Resources.FindObjectsOfTypeAll<DialogueRunner>().Where(r => r.gameObject.scene.IsValid()).ToArray();
        modalGroups = Resources.FindObjectsOfTypeAll<CanvasGroup>()
            .Where(g => g.gameObject.scene.IsValid() && HasAncestor(g.transform, "UI_DialogBG")).ToArray();
    }

    internal bool Alive => Dock != null && Hud != null && Font != null && runners.Any(r => r != null);
    internal bool CanInteract
    {
        get
        {
            if (!Alive || !Dock.gameObject.activeInHierarchy) return false;
            for (var parent = Dock.transform; parent != null; parent = parent.parent)
            {
                var group = parent.GetComponent<CanvasGroup>();
                if (group != null && (group.alpha < .05f || !group.interactable)) return false;
            }
            foreach (var runner in runners)
                if (runner != null && runner.IsDialogueRunning) return false;
            foreach (var group in modalGroups)
                if (group != null && group.gameObject.activeInHierarchy && group.alpha > .05f && group.blocksRaycasts)
                    return false;
            return runners.Any(r => r != null);
        }
    }

    internal static NativeGameUi TryFind()
    {
        var dock = Resources.FindObjectsOfTypeAll<RectTransform>().FirstOrDefault(r =>
            r.name == "Left_DownArea" && r.gameObject.scene.IsValid() && HasAncestor(r, "MainUI_Root"));
        if (dock == null) return null;
        var sprites = new Dictionary<string, Sprite>();
        foreach (var sprite in Resources.FindObjectsOfTypeAll<Sprite>())
            if (sprite != null && !sprites.ContainsKey(sprite.name)) sprites.Add(sprite.name, sprite);
        if (new[] { "Button", "AnswerBase", "TalkWindow", "WindowBase2" }
            .Any(name => !sprites.ContainsKey(name))) return null;
        var talkIcon = new[] { "Icon_Story", "Icon_Log", "Cursor_Talk" }.FirstOrDefault(sprites.ContainsKey);
        if (talkIcon == null) return null;
        sprites["CompanionTalkIcon"] = sprites[talkIcon];
        // Read font metadata only from the known HUD dock, never text from
        // notes, ToDo entries or other editable game views.
        var label = dock.GetComponentInChildren<TextMeshProUGUI>(true);
        // Dialog body uses the game's Chinese medium face, not whichever bold
        // HUD caption happens to be enumerated first. Keep its native fallback.
        var font = Resources.FindObjectsOfTypeAll<TMP_FontAsset>().FirstOrDefault(f =>
            f != null && f.name.Contains("NotoSansSC-Medium", StringComparison.OrdinalIgnoreCase))
            ?? (label != null ? label.font : TMP_Settings.defaultFontAsset);
        return font == null ? null : new NativeGameUi(dock, font, sprites);
    }

    private static bool HasAncestor(Transform node, string name)
    {
        for (; node != null; node = node.parent)
            if (node.name == name || node.name == name + "(Clone)") return true;
        return false;
    }

    internal Image Image(RectTransform rect, string name, bool hit = false, float density = 1)
    {
        var image = rect.gameObject.AddComponent<Image>();
        image.sprite = sprites.GetValueOrDefault(name);
        image.type = image.sprite != null && image.sprite.border != Vector4.zero ? UnityEngine.UI.Image.Type.Sliced : UnityEngine.UI.Image.Type.Simple;
        image.pixelsPerUnitMultiplier = density;
        image.raycastTarget = hit;
        image.color = Color.white;
        return image;
    }

    internal void StyleButton(Button button, Image image)
    {
        button.targetGraphic = image;
        button.transition = Selectable.Transition.SpriteSwap;
        button.spriteState = new SpriteState {
            highlightedSprite = sprites.GetValueOrDefault("AnswerBase_Hight"),
            pressedSprite = sprites.GetValueOrDefault("AnswerBase_Pushed"),
            selectedSprite = sprites.GetValueOrDefault("AnswerBase_Selected")
        };
        var navigation = button.navigation;
        navigation.mode = Navigation.Mode.None;
        button.navigation = navigation;
    }
}
