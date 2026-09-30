using System;
using System.IO;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;

[assembly: AssemblyTitle("FLOWDEV FRAME")]
[assembly: AssemblyDescription("FRAME - Quantitative Deep Learning Trading Cockpit")]
[assembly: AssemblyConfiguration("")]
[assembly: AssemblyCompany("FLOWDEV ALIFHAIKAL")]
[assembly: AssemblyProduct("FRAME Desktop Terminal")]
[assembly: AssemblyCopyright("Copyright © 2026")]
[assembly: AssemblyFileVersion("1.0.0.0")]
[assembly: AssemblyVersion("1.0.0.0")]

namespace FlowDevFrame
{
    class Program
    {
        [DllImport("kernel32.dll")]
        static extern IntPtr GetConsoleWindow();

        [DllImport("user32.dll")]
        static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

        const int SW_HIDE = 0;

        static void Main(string[] args)
        {
            // Hide console if any was attached
            IntPtr hWnd = GetConsoleWindow();
            if (hWnd != IntPtr.Zero)
            {
                ShowWindow(hWnd, SW_HIDE);
            }

            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string venvPythonw = Path.Combine(baseDir, ".venv", "Scripts", "pythonw.exe");
            string venvPython = Path.Combine(baseDir, ".venv", "Scripts", "python.exe");
            string scriptPath = Path.Combine(baseDir, "FRAME.py");

            string pythonExe = File.Exists(venvPythonw) ? venvPythonw : venvPython;

            if (!File.Exists(pythonExe))
            {
                System.Windows.Forms.MessageBox.Show(
                    "Python runtime not found in .venv\\Scripts!\nPlease run Install_FRAME.bat first.",
                    "FLOWDEV FRAME - Setup Required",
                    System.Windows.Forms.MessageBoxButtons.OK,
                    System.Windows.Forms.MessageBoxIcon.Error
                );
                return;
            }

            if (!File.Exists(scriptPath))
            {
                System.Windows.Forms.MessageBox.Show(
                    "Master application file FRAME.py not found in:\n" + baseDir,
                    "FLOWDEV FRAME - Missing Module",
                    System.Windows.Forms.MessageBoxButtons.OK,
                    System.Windows.Forms.MessageBoxIcon.Error
                );
                return;
            }

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonExe;
            psi.Arguments = "\"" + scriptPath + "\"";
            psi.WorkingDirectory = baseDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.WindowStyle = ProcessWindowStyle.Hidden;

            // Forward arguments if any
            if (args != null && args.Length > 0)
            {
                psi.Arguments += " " + string.Join(" ", args);
            }

            try
            {
                Process.Start(psi);
            }
            catch (Exception ex)
            {
                System.Windows.Forms.MessageBox.Show(
                    "Failed to launch FRAME:\n" + ex.Message,
                    "FLOWDEV FRAME - Launch Error",
                    System.Windows.Forms.MessageBoxButtons.OK,
                    System.Windows.Forms.MessageBoxIcon.Error
                );
            }
        }
    }
}
