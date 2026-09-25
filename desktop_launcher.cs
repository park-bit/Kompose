using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Windows.Forms;

namespace Kompose
{
    static class Program
    {
        private static Process backendProcess = null;
        private static Process frontendProcess = null;
        private static NotifyIcon trayIcon;

        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string rootDir = AppDomain.CurrentDomain.BaseDirectory;
            // Handle if rootDir is inside bin or similar
            if (!File.Exists(Path.Combine(rootDir, "docker-compose.yml")))
            {
                DirectoryInfo parentInfo = Directory.GetParent(rootDir);
                string parent = parentInfo != null ? parentInfo.FullName : null;
                if (parent != null && File.Exists(Path.Combine(parent, "docker-compose.yml")))
                {
                    rootDir = parent;
                }
            }

            // Start Tray Icon
            trayIcon = new NotifyIcon();
            trayIcon.Text = "Kompose - AI Travel Planner";
            trayIcon.Icon = System.Drawing.SystemIcons.Application;
            trayIcon.Visible = true;

            ContextMenuStrip menu = new ContextMenuStrip();
            menu.Items.Add("Open Kompose App", null, (s, e) => LaunchAppWindow());
            menu.Items.Add("Restart Services", null, (s, e) => RestartServices(rootDir));
            menu.Items.Add("-");
            menu.Items.Add("Exit", null, (s, e) => ExitApplication());
            trayIcon.ContextMenuStrip = menu;

            // Start backend if not running
            EnsureBackendRunning(rootDir);

            // Start frontend if not running
            EnsureFrontendRunning(rootDir);

            // Wait for frontend to respond
            WaitForUrl("http://localhost:3000", 25);

            // Launch native desktop window (Edge App mode)
            LaunchAppWindow();

            Application.Run();
        }

        static bool IsPortInUse(int port)
        {
            try
            {
                using (TcpClient client = new TcpClient())
                {
                    IAsyncResult result = client.BeginConnect("127.0.0.1", port, null, null);
                    bool success = result.AsyncWaitHandle.WaitOne(400);
                    if (success)
                    {
                        client.EndConnect(result);
                        return true;
                    }
                }
            }
            catch { }
            return false;
        }

        static void EnsureBackendRunning(string rootDir)
        {
            if (IsPortInUse(8000))
            {
                return; // already active
            }

            string pythonExe = Path.Combine(rootDir, "backend", "venv", "Scripts", "python.exe");
            if (!File.Exists(pythonExe))
            {
                pythonExe = "python";
            }

            string backendDir = Path.Combine(rootDir, "backend");

            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = pythonExe,
                Arguments = "-m uvicorn app.main:app --host 127.0.0.1 --port 8000",
                WorkingDirectory = backendDir,
                CreateNoWindow = true,
                UseShellExecute = false,
            };

            try
            {
                backendProcess = Process.Start(psi);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Could not start Kompose Backend: " + ex.Message, "Kompose Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        static void EnsureFrontendRunning(string rootDir)
        {
            if (IsPortInUse(3000))
            {
                return; // already active
            }

            string frontendDir = Path.Combine(rootDir, "frontend");

            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = "/c npm run dev",
                WorkingDirectory = frontendDir,
                CreateNoWindow = true,
                UseShellExecute = false,
            };

            try
            {
                frontendProcess = Process.Start(psi);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Could not start Kompose Frontend: " + ex.Message, "Kompose Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        static void WaitForUrl(string url, int timeoutSeconds)
        {
            for (int i = 0; i < timeoutSeconds * 2; i++)
            {
                try
                {
                    HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
                    request.Timeout = 800;
                    using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                    {
                        if (response.StatusCode == HttpStatusCode.OK) return;
                    }
                }
                catch { }
                Thread.Sleep(500);
            }
        }

        static void LaunchAppWindow()
        {
            // Try launching Edge in standalone application window mode
            string edgePath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                "Microsoft", "Edge", "Application", "msedge.exe"
            );

            if (!File.Exists(edgePath))
            {
                edgePath = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                    "Microsoft", "Edge", "Application", "msedge.exe"
                );
            }

            if (File.Exists(edgePath))
            {
                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = edgePath,
                    Arguments = "--app=http://localhost:3000 --window-size=1280,840 --name=Kompose",
                    UseShellExecute = false
                };
                Process.Start(psi);
            }
            else
            {
                // Fallback to default browser
                Process.Start("http://localhost:3000");
            }
        }

        static void RestartServices(string rootDir)
        {
            try
            {
                if (backendProcess != null && !backendProcess.HasExited) backendProcess.Kill();
                if (frontendProcess != null && !frontendProcess.HasExited) frontendProcess.Kill();
            }
            catch { }

            EnsureBackendRunning(rootDir);
            EnsureFrontendRunning(rootDir);
            WaitForUrl("http://localhost:3000", 15);
            LaunchAppWindow();
        }

        static void ExitApplication()
        {
            trayIcon.Visible = false;
            try
            {
                if (backendProcess != null && !backendProcess.HasExited) backendProcess.Kill();
                if (frontendProcess != null && !frontendProcess.HasExited) frontendProcess.Kill();
            }
            catch { }
            Application.Exit();
        }
    }
}
