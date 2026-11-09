// Session-only navigation state. No prompts or paths are written to web storage.
export const libraryViewState={searchQuery:'',sortBy:'newest',kindFilter:'all',visibility:'active',page:0,scrollTop:0};

export function groupVersionFamilies(rows) {
  const byId=new Map();for(const row of rows)for(const id of [row.id,...(row.aliasIds||[])])byId.set(id,row);
  const rootOf=row=>{
    let current=row;const seen=new Set([row.id]);
    for(let depth=0;depth<100;depth++){
      const parents=[...new Set([current.parentId,...(current.aliasMetadata||[]).map(x=>x.parentId)].filter(Boolean))];
      if(parents.length!==1||!byId.has(parents[0]))return current.id;
      const parent=byId.get(parents[0]);if(seen.has(parent.id))return row.id;
      seen.add(parent.id);current=parent;
    }
    return row.id; // Uncertain/cyclic lineage is never silently collapsed.
  };
  const groups=new Map();for(const row of rows){const root=rootOf(row);if(!groups.has(root))groups.set(root,[]);groups.get(root).push(row);}
  return [...groups.values()].map(members=>({...members[0],versionCount:members.length,familyIds:members.map(x=>x.id)}));
}
