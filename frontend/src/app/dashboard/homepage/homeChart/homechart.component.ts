import { CommonModule } from "@angular/common";
import { Component } from "@angular/core";
import { RouterModule } from "@angular/router";

@Component({
    selector: 'homeChart', // Use the new selector
    standalone: true,
    imports: [
        CommonModule,
        RouterModule, // For routerLink
        // MatGridListModule, // Preserved old import
        // MatButtonModule, // Preserved old import
    ],
    templateUrl: './homechart.component.html',
    styleUrls: ['./homechart.component.scss'],
})
export class HomeChartComponent  {

}