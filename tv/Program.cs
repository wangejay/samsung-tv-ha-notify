// Derived from als7294/overscreen (tvoverlay), commit
// c0fd412bec1a5a82f1d6a4cf867d3eb0281e55da. GNU GPL v3; see ../licenses/GPL-3.0.txt.
// Local changes: retain NUI wrappers, enforce a seven-second lifetime, and clean up
// timers, animations, views and temporary images after expiry or errors.
// Notification windows are transparent and non-focusable: the remote continues
// controlling the application underneath. The LAN relay renders transparent PNGs.
//
// Protocol (LAN, UDP 18110): {"id":"..","url":"http://<relay>:8795/media/x.png","x":..,"y":..,"w":..,"h":..,"ms":..}
// The image must come from the sender's own address. Reply: "ack <id>" once downloaded.
using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using Tizen.NUI;
using Tizen.NUI.BaseComponents;
using Timer = Tizen.NUI.Timer;

namespace SmittyOverlay
{
    internal sealed class Overlay : NUIApplication
    {
        private sealed class Req { public string Path; public int X, Y, W, H, Ms; }

        private readonly ConcurrentQueue<Req> inbox = new ConcurrentQueue<Req>();
        private readonly HttpClient http = new HttpClient { Timeout = TimeSpan.FromSeconds(6) };
        private Timer pump;
        private bool busy;
        // NUI wrappers must remain rooted until the notification is closed.
        private Window currentWindow;
        private View currentRoot;
        private ImageView currentImage;
        private Animation enterAnimation;
        private Timer holdTimer;
        private Animation exitAnimation;
        private Req currentRequest;
        private readonly Stopwatch visibleFor = new Stopwatch();
        private bool exiting;
        private bool closeRequested;

        private void Listen()
        {
            using (var udp = new UdpClient(18110))
            {
                var from = new IPEndPoint(IPAddress.Any, 0);
                while (true)
                {
                    try
                    {
                        var data = udp.Receive(ref from);
                        var j = JsonDocument.Parse(data).RootElement;
                        string url = j.GetProperty("url").GetString() ?? "";
                        if (!url.StartsWith("http://" + from.Address + ":")) continue; // only the sender's own images
                        int I(string k, int d) => j.TryGetProperty(k, out var v) && v.TryGetInt32(out var n) ? n : d;
                        var req = new Req { X = I("x", 0), Y = I("y", 0), W = Math.Clamp(I("w", 1000), 10, 1920), H = Math.Clamp(I("h", 200), 10, 1080), Ms = Math.Clamp(I("ms", 7000), 1000, 7000) };
                        req.Path = System.IO.Path.Combine(Tizen.Applications.Application.Current.DirectoryInfo.Data, "pill-" + DateTime.Now.Ticks + ".png");
                        File.WriteAllBytes(req.Path, http.GetByteArrayAsync(url).Result);
                        inbox.Enqueue(req);
                        var ack = Encoding.UTF8.GetBytes("ack " + (j.TryGetProperty("id", out var id) ? id.GetString() : ""));
                        udp.Send(ack, ack.Length, from);
                    }
                    catch (Exception) { /* Ignore malformed requests and failed downloads. */ }
                }
            }
        }

        private void Show(Req r)
        {
            busy = true;
            currentRequest = r;
            exiting = false;
            closeRequested = false;
            visibleFor.Restart();
            try
            {
                currentWindow = new Window("SmittyOverlay", new Rectangle(r.X, r.Y, r.W, r.H), true);
                currentWindow.Type = WindowType.Notification;
                currentWindow.BackgroundColor = Color.Transparent;
                currentWindow.SetTransparency(true);
                currentWindow.SetOpaqueState(false);
                currentWindow.SetAcceptFocus(false);           // the remote keeps controlling the app underneath
                currentWindow.SetNotificationLevel(NotificationLevel.Base);
                currentRoot = new View { Size = new Size(r.W, r.H), BackgroundColor = Color.Transparent, Opacity = 0.0f, PositionY = -22 };
                currentImage = new ImageView { Size = new Size(r.W, r.H), BackgroundColor = Color.Transparent, SynchronousLoading = true };
                currentImage.SetImage(r.Path);
                currentRoot.Add(currentImage);
                currentWindow.Add(currentRoot);
                currentWindow.Show();
                // The requested duration includes the 320 ms exit animation.
                enterAnimation = new Animation(420);
                enterAnimation.AnimateTo(currentRoot, "Opacity", 1.0f);
                enterAnimation.AnimateTo(currentRoot, "PositionY", 0.0f, new AlphaFunction(AlphaFunction.BuiltinFunctions.EaseOut));
                enterAnimation.Play();
                holdTimer = new Timer((uint)(r.Ms - 320));
                holdTimer.Tick += OnHoldTick;
                holdTimer.Start();
                Console.WriteLine("SmittyOverlay: shown, duration=" + r.Ms + "ms");
            }
            catch (Exception ex)
            {
                Console.WriteLine("SmittyOverlay: show failed: " + ex.Message);
                CloseCurrent();
            }
        }

        private bool OnHoldTick(object sender, Timer.TickEventArgs e)
        {
            BeginExit();
            return false;
        }

        private void BeginExit()
        {
            if (!busy || exiting) return;
            exiting = true;
            try
            {
                enterAnimation?.Stop();
                exitAnimation = new Animation(320);
                exitAnimation.AnimateTo(currentRoot, "Opacity", 0.0f);
                exitAnimation.AnimateTo(currentRoot, "PositionY", -16.0f, new AlphaFunction(AlphaFunction.BuiltinFunctions.EaseIn));
                exitAnimation.Finished += OnExitFinished;
                exitAnimation.Play();
            }
            catch (Exception ex)
            {
                Console.WriteLine("SmittyOverlay: exit failed: " + ex.Message);
                closeRequested = true;
            }
        }

        // Dispose wrappers on the next pump tick, outside native event callbacks.
        private void OnExitFinished(object sender, EventArgs e) => closeRequested = true;

        private static void TryCleanup(Action action)
        {
            try { action(); }
            catch (Exception ex) { Console.WriteLine("SmittyOverlay: cleanup: " + ex.Message); }
        }

        private void CloseCurrent()
        {
            // Hide first; a failed animation or disposal must never leave the banner visible.
            if (currentWindow != null) TryCleanup(() => currentWindow.Hide());
            if (holdTimer != null)
            {
                TryCleanup(() => holdTimer.Tick -= OnHoldTick);
                TryCleanup(() => holdTimer.Stop());
                TryCleanup(() => holdTimer.Dispose());
                holdTimer = null;
            }
            if (enterAnimation != null)
            {
                TryCleanup(() => enterAnimation.Stop());
                TryCleanup(() => enterAnimation.Dispose());
                enterAnimation = null;
            }
            if (exitAnimation != null)
            {
                TryCleanup(() => exitAnimation.Finished -= OnExitFinished);
                TryCleanup(() => exitAnimation.Stop());
                TryCleanup(() => exitAnimation.Dispose());
                exitAnimation = null;
            }
            if (currentRoot != null && currentImage != null) TryCleanup(() => currentRoot.Remove(currentImage));
            if (currentWindow != null && currentRoot != null) TryCleanup(() => currentWindow.Remove(currentRoot));
            if (currentImage != null) TryCleanup(() => currentImage.Dispose());
            if (currentRoot != null) TryCleanup(() => currentRoot.Dispose());
            if (currentWindow != null) TryCleanup(() => currentWindow.Dispose());
            if (currentRequest != null) TryCleanup(() => File.Delete(currentRequest.Path));
            currentImage = null;
            currentRoot = null;
            currentWindow = null;
            currentRequest = null;
            visibleFor.Reset();
            exiting = false;
            closeRequested = false;
            busy = false;
            Console.WriteLine("SmittyOverlay: closed");
        }

        protected override void OnCreate()
        {
            base.OnCreate();
            // No screen of its own: the main window stays (hiding it gets the app closed) but is
            // fully transparent, click-through and sent behind everything.
            var main = GetDefaultWindow();
            main.BackgroundColor = Color.Transparent;
            main.SetTransparency(true);
            main.SetOpaqueState(false);
            main.SetAcceptFocus(false);
            main.Lower();
            new Thread(Listen) { IsBackground = true }.Start();
            pump = new Timer(80);
            pump.Tick += (s, e) =>
            {
                // Independent deadline: neither a missed hold Tick nor a missed animation
                // Finished event can keep a window alive beyond its requested duration.
                if (busy && (closeRequested || visibleFor.ElapsedMilliseconds >= currentRequest.Ms)) CloseCurrent();
                else if (busy && visibleFor.ElapsedMilliseconds >= currentRequest.Ms - 320) BeginExit();
                if (!busy && inbox.TryDequeue(out var r)) Show(r);
                return true;
            };
            pump.Start();
        }

        private static void Main(string[] args) => new Overlay().Run(args);
    }
}
