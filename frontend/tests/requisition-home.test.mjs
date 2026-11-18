import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import React from 'react';
import * as jsxRuntime from 'react/jsx-runtime';
import TestRenderer,{act} from 'react-test-renderer';
import {transformSync} from 'esbuild';
import * as staff from '../src/utils/staff-portal.mjs';
const compiled=transformSync(fs.readFileSync(new URL('../src/pages/StaffPortal.jsx',import.meta.url),'utf8'),{loader:'jsx',format:'cjs',jsx:'automatic'}).code;
const text=node=>typeof node==='string'?node:node?.children?.map(text).join('')||'';
for(const role of ['EmployeeUser','ManagerUser']) {
  test(role+' sees Requisitions in the home block grid with no sidebar',async()=>{
    globalThis.window={location:{search:'',href:'https://example.test/'},addEventListener(){},removeEventListener(){}};
    const module={exports:{}};
    new Function('require','module','exports',compiled)(name=>{
      if(name==='react')return React;
      if(name==='react/jsx-runtime')return jsxRuntime;
      if(name==='../api/client')return{apiRequest:async()=>({can_import:false})};
      if(name==='../utils/staff-portal.mjs')return staff;
      if(name==='../utils/requisitions')return{useRequisitionsAccess:()=>true,useMortuaryAccess:()=>true};
      if(name==='../utils/useCommissionMonth')return{useCommissionMonth:()=>['2026-11']};
      if(name==='../embeddedAttendance')return{};
      if(name.endsWith('.css'))return{};
      return{__esModule:true,default:()=>null,MortuaryBookUpload:()=>null};
    },module,module.exports);
    let view;await act(async()=>{view=TestRenderer.create(React.createElement(module.exports.default,{me:{id:2,roles:[role]},onLogout(){}}));});
    try{
      assert.equal(view.root.findAllByType('aside').length,0);
      const grid=view.root.findByProps({className:'staff-button-grid'});
      assert.ok(grid.findAllByType('button').some(button=>text(button)==='Requisitions'));
      assert.equal(grid.findAllByType('button').filter(button=>text(button)==='Mortuary book').length,0,'requisition uploads already share commission evidence');
      assert.equal(staff.staffRoute('?staff_portal_page=mortuary'),'mortuary');
    }finally{view.unmount();}
  });
}
