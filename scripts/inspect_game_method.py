"""Print original managed method IL with resolved field/method names."""
import sys
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBytes
sys.stdout.reconfigure(encoding='utf-8')
pe=dnfile.dnPE('C:/Games/Tyranny/Data/Managed/Assembly-CSharp.dll')
names={}
for t in pe.net.mdtables.TypeDef:
    for f in t.FieldList:names[id(f.row)]=str(t.TypeName)+'.'+str(f.row.Name)
    for m in t.MethodList:names[id(m.row)]=str(t.TypeName)+'.'+str(m.row.Name)
for t in pe.net.mdtables.TypeDef:
    if str(t.TypeName)!=sys.argv[1]:continue
    for m in t.MethodList:
        if len(sys.argv)>2 and str(m.row.Name)!=sys.argv[2]:continue
        if not m.row.Rva:continue
        print(names[id(m.row)])
        for i in CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(m.row.Rva))).instructions:
            operand=i.operand
            if hasattr(operand,'table'):
                table=pe.net.mdtables.tables.get(operand.table)
                if table and operand.rid<=len(table.rows):
                    row=table.rows[operand.rid-1];operand=names.get(id(row),str(getattr(row,'Name',operand)))
            print(i.offset,i.opcode.name,operand)
