#include <SDL.h>
#include <SDL_opengl.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <optional>
#include <string>

namespace {

constexpr double kTickSeconds = 1.0 / 60.0;
constexpr float kMoveSpeed = 0.65F;

struct Unit {
    float x = 0.0F;
    float y = 0.0F;
    float goal_x = 0.0F;
    float goal_y = 0.0F;
    bool moving = false;
};

struct Options {
    std::filesystem::path installation;
    std::string battle;
};

std::optional<Options> parse_options(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Usage: horned-rat-engine <WARFB installation> <BFxxx.BTS>\n";
        return std::nullopt;
    }
    return Options{argv[1], argv[2]};
}

bool valid_installation(const std::filesystem::path& installation) {
    return std::filesystem::is_directory(installation / "FILE")
        && std::filesystem::is_directory(installation / "FILE" / "SCRIPT");
}

void tick(Unit& unit) {
    if (!unit.moving) {
        return;
    }
    const float dx = unit.goal_x - unit.x;
    const float dy = unit.goal_y - unit.y;
    const float distance = std::hypot(dx, dy);
    const float step = kMoveSpeed * static_cast<float>(kTickSeconds);
    if (distance <= step) {
        unit.x = unit.goal_x;
        unit.y = unit.goal_y;
        unit.moving = false;
        return;
    }
    unit.x += dx / distance * step;
    unit.y += dy / distance * step;
}

void draw_unit(const Unit& unit) {
    glPushMatrix();
    glTranslatef(unit.x, unit.y, 0.0F);
    glColor3f(unit.moving ? 0.95F : 0.25F, unit.moving ? 0.75F : 0.55F, 0.25F);
    glBegin(GL_TRIANGLES);
    glVertex2f(0.0F, 0.06F);
    glVertex2f(-0.045F, -0.04F);
    glVertex2f(0.045F, -0.04F);
    glEnd();
    glPopMatrix();
}

void draw_scene(const Unit& unit, int width, int height) {
    glViewport(0, 0, width, height);
    glClearColor(0.08F, 0.10F, 0.12F, 1.0F);
    glClear(GL_COLOR_BUFFER_BIT);
    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glOrtho(-0.75, 0.75, -0.5, 0.5, -1.0, 1.0);
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();

    glColor3f(0.2F, 0.25F, 0.22F);
    glBegin(GL_LINES);
    for (int i = -7; i <= 7; ++i) {
        const float x = static_cast<float>(i) / 10.0F;
        glVertex2f(x, -0.5F);
        glVertex2f(x, 0.5F);
    }
    for (int i = -5; i <= 5; ++i) {
        const float y = static_cast<float>(i) / 10.0F;
        glVertex2f(-0.75F, y);
        glVertex2f(0.75F, y);
    }
    glEnd();
    draw_unit(unit);
}

}  // namespace

int main(int argc, char** argv) {
    const auto options = parse_options(argc, argv);
    if (!options) {
        return 2;
    }
    if (!valid_installation(options->installation)) {
        std::cerr << "Not a WARFB installation: " << options->installation << '\n';
        return 2;
    }
    std::cout << "Prototype battle: " << options->battle << "\n"
              << "Click to issue a move order; Escape quits.\n";

    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        std::cerr << "SDL initialization failed: " << SDL_GetError() << '\n';
        return 1;
    }
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 1);
    SDL_Window* window = SDL_CreateWindow(
        "Open Horned Rat - movement prototype", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        960, 640, SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE
    );
    if (window == nullptr) {
        std::cerr << "Window creation failed: " << SDL_GetError() << '\n';
        SDL_Quit();
        return 1;
    }
    SDL_GLContext context = SDL_GL_CreateContext(window);
    if (context == nullptr) {
        std::cerr << "OpenGL context creation failed: " << SDL_GetError() << '\n';
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 1;
    }
    SDL_GL_SetSwapInterval(1);

    Unit unit;
    bool running = true;
    double accumulator = 0.0;
    std::uint64_t previous = SDL_GetPerformanceCounter();
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event) != 0) {
            if (event.type == SDL_QUIT || (event.type == SDL_KEYDOWN && event.key.keysym.sym == SDLK_ESCAPE)) {
                running = false;
            } else if (event.type == SDL_MOUSEBUTTONDOWN && event.button.button == SDL_BUTTON_LEFT) {
                int width = 0;
                int height = 0;
                SDL_GetWindowSize(window, &width, &height);
                unit.goal_x = (static_cast<float>(event.button.x) / static_cast<float>(width) - 0.5F) * 1.5F;
                unit.goal_y = (0.5F - static_cast<float>(event.button.y) / static_cast<float>(height)) * 1.0F;
                unit.moving = true;
            }
        }
        const std::uint64_t now = SDL_GetPerformanceCounter();
        accumulator += static_cast<double>(now - previous) / static_cast<double>(SDL_GetPerformanceFrequency());
        previous = now;
        accumulator = std::min(accumulator, 0.25);
        while (accumulator >= kTickSeconds) {
            tick(unit);
            accumulator -= kTickSeconds;
        }
        int width = 0;
        int height = 0;
        SDL_GetWindowSize(window, &width, &height);
        draw_scene(unit, width, height);
        SDL_GL_SwapWindow(window);
    }

    SDL_GL_DeleteContext(context);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
