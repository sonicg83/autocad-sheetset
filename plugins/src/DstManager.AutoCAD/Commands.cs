using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

[assembly: CommandClass(typeof(DstManager.AutoCAD.Commands))]

namespace DstManager.AutoCAD
{
    public sealed class Commands
    {
        [CommandMethod("DstDeleteLayouts")]
        public void DeleteLayouts()
        {
            Document document = Application.DocumentManager.MdiActiveDocument;
            Database database = document.Database;
            LayoutManager manager = LayoutManager.Current;
            manager.CurrentLayout = "Model";
            var names = new List<string>();
            using (Transaction transaction = database.TransactionManager.StartTransaction())
            {
                var layouts = (DBDictionary)transaction.GetObject(database.LayoutDictionaryId, OpenMode.ForRead);
                foreach (DBDictionaryEntry entry in layouts)
                {
                    if (!string.Equals(entry.Key, "Model", StringComparison.OrdinalIgnoreCase))
                        names.Add(entry.Key);
                }
                transaction.Commit();
            }
            foreach (string name in names)
                manager.DeleteLayout(name);
            document.Editor.WriteMessage("\nDST_MANAGER_LAYOUTS_DELETED={0}", names.Count);
        }

        [CommandMethod("DstDeleteDefaultLayout")]
        public void DeleteDefaultLayout()
        {
            Document document = Application.DocumentManager.MdiActiveDocument;
            Database database = document.Database;
            string candidate = null;
            int paperLayoutCount = 0;
            using (Transaction transaction = database.TransactionManager.StartTransaction())
            {
                var layouts = (DBDictionary)transaction.GetObject(database.LayoutDictionaryId, OpenMode.ForRead);
                foreach (DBDictionaryEntry entry in layouts)
                {
                    if (string.Equals(entry.Key, "Model", StringComparison.OrdinalIgnoreCase)) continue;
                    paperLayoutCount++;
                    if (string.Equals(entry.Key, "Layout1", StringComparison.OrdinalIgnoreCase) || entry.Key == "布局1")
                        candidate = entry.Key;
                }
                transaction.Abort();
            }
            if (paperLayoutCount > 1 && candidate != null)
                LayoutManager.Current.DeleteLayout(candidate);
        }

        [CommandMethod("DstGetLayoutHandles")]
        public void GetLayoutHandles()
        {
            Document document = Application.DocumentManager.MdiActiveDocument;
            Database database = document.Database;
            var rows = new List<string>();
            using (Transaction transaction = database.TransactionManager.StartTransaction())
            {
                var layouts = (DBDictionary)transaction.GetObject(database.LayoutDictionaryId, OpenMode.ForRead);
                foreach (DBDictionaryEntry entry in layouts)
                {
                    if (!string.Equals(entry.Key, "Model", StringComparison.OrdinalIgnoreCase))
                        rows.Add(entry.Key + "=" + entry.Value.Handle.ToString());
                }
                transaction.Abort();
            }
            rows.Sort(StringComparer.Ordinal);
            string output = Path.Combine(Path.GetDirectoryName(database.Filename), Path.GetFileNameWithoutExtension(database.Filename) + ".dst-handles.txt");
            File.WriteAllLines(output, rows, new UTF8Encoding(false));
            document.Editor.WriteMessage("\nDST_MANAGER_HANDLES={0}", rows.Count);
        }
    }
}
