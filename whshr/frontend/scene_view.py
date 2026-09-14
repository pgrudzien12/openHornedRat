"""Base scene views: a view draws one scene instance and translates raw input into its scene events."""


class SceneView:
    """Base view. A view owns GPU resources for one scene instance and releases them when replaced."""

    background = (18, 18, 24)

    def __init__(self, gpu, scene, options=None):
        self.gpu = gpu
        self.scene = scene
        self.options = options or {}

    def events(self, event):
        """Return the scene events produced by one pygame event."""
        return ()

    def animate(self, seconds):
        """Advance presentation-only state (camera, animation clocks) by the frame duration."""

    def status(self):
        """Extra debug overlay lines."""
        return ()

    def draw(self):
        self.gpu.target.clear(self.background)

    def release(self):
        """Release GPU resources owned by this view."""


class PlaceholderView(SceneView):
    """Names a scene whose real presentation is not implemented yet."""

    def __init__(self, gpu, scene, options=None, hint=""):
        super().__init__(gpu, scene, options)
        self.label = gpu.text((720, 120), gpu.title_font, background=None)
        self.label.set_lines((type(scene).__name__, hint))

    def draw(self):
        super().draw()
        (width, height), (text_width, text_height) = self.gpu.target.size, self.label.text_size
        self.label.draw((width - text_width) // 2, (height - text_height) // 2)

    def release(self):
        self.label.release()
