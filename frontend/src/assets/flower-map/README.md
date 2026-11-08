# Flower map artwork

Source: [HC, frame 64:20526](https://www.figma.com/design/ILn1JWwC6JSx09ma2EaOMj/HC?node-id=64-20526).

The eight petal sets come from nodes 64:22368 (blue), 64:22336 (magenta),
64:22344 (sky), 64:22360 (orange), 64:22320 (cyan), 64:22328 (purple),
64:22376 (indigo), and 64:22352 (periwinkle). All nine original branch
layers are included. Navigation icons come from the frame's header.
These are the original exported SVG files.

`src/map/flowerArtwork.ts` records each layer's exact Figma affine transform.
`flowerScene.ts` holds the 1680 × 1029 map frame, flower bounds, and label
positions. `flowerBloom.ts` composes these layers once into cached canvases,
then scales the entire scene uniformly when fitting or zooming. SVG intrinsic
sizes, blur extents, reflections, and rotations are preserved.

The overview displays the eight largest vulnerability clusters, with ties ordered
alphabetically. Search and repository selection bring a matching smaller group
into an existing scene slot, retaining the positions of other visible groups.
Clearing the search restores the overview; smaller groups remain searchable and
selectable from Findings even when absent from the overview.
No temporary Figma asset URL is needed at runtime.
