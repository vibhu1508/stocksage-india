import { Pipe, PipeTransform } from '@angular/core';

/** "Tata Motors Passenger Vehicles Limited" -> "... Ltd": company names everywhere take less room. */
export function shortCompanyName(name: string | null | undefined): string {
  return (name ?? '').replace(/\bLIMITED\b/g, 'LTD').replace(/\blimited\b/gi, 'Ltd');
}

@Pipe({ name: 'shortName', standalone: true })
export class ShortNamePipe implements PipeTransform {
  transform(name: string | null | undefined): string {
    return shortCompanyName(name);
  }
}
