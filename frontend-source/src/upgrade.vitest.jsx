import React from 'react';
import {test,expect} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {SelectField} from './controls.jsx';
import {LocalDisplayPreferences,DiagnosticValue,ResponseDrawer} from './upgrade.jsx';
test('select adapter renders an accessible themed combobox, not a native popup',()=>{
 const {container}=render(<SelectField aria-label="Canvas" value="square"><option value="square">Square</option><option value="wide">Wide</option></SelectField>);
 expect(screen.getByRole('combobox',{name:'Canvas'}).textContent).toContain('Square');expect(container.querySelector('select:not([aria-hidden=true])')).toBeNull();
});
test('long diagnostics cannot expand the value column; full value stays available',()=>{
 const value='abc123'.repeat(20);render(<dl><DiagnosticValue value={value}/></dl>);
 expect(screen.getByTitle(value).textContent.length).toBeLessThan(40);expect(screen.getByRole('button',{name:'Copy full diagnostic value'})).toBeTruthy();
});
test('closed details are absent from the message flow',()=>{
 const {container}=render(<ResponseDrawer open={false} onClose={()=>{}}><p>Private developer measurement</p></ResponseDrawer>);
 expect(container.textContent).not.toContain('Private developer measurement');
});
test('developer toggle persists only a UI-local preference',()=>{
 render(<LocalDisplayPreferences/>);fireEvent.click(screen.getByRole('switch'));expect(JSON.parse(localStorage.getItem('offlinegpt-ui-developer'))).toBe(true);expect(document.documentElement.dataset.developer).toBe('true');
});
